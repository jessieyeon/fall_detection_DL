#!/usr/bin/env python3
"""전시 트래픽 시뮬레이터 — 배포 전에 터뜨려 보고 한도를 정한다.

    python3 scripts/load_test.py http://localhost:8000 --users 50 --seconds 30
    python3 scripts/load_test.py https://내주소 --users 100 --seconds 60

가상 관람객 한 명은 실제 관람객이 하는 일을 그대로 한다:
로그인 → 첫 화면 → 설문/리포트 조회 → 실시간 화면(상태 폴링 1.5초 간격) → 나감.

분석 업로드는 여기에 넣지 않는다. 그건 이미 따로 측정했고(동시 14건 → 8 수락/6 거절),
CPU 를 크게 써서 다른 측정을 다 가려버린다.

종료 코드: 5xx·타임아웃이 하나라도 있거나 p95 가 --slo 를 넘으면 1.
"""

import argparse
import asyncio
import random
import sys
import time

try:
    import httpx
except ImportError:
    sys.exit("httpx 가 필요합니다:  pip install httpx")

TIMEOUT_STATUS = 599            # 타임아웃·연결실패에 우리가 붙이는 코드


def percentile(xs, p):
    """선형 보간 백분위수. 스크립트에 numpy 를 끌어오지 않으려고 직접 구현."""
    if not xs:
        return 0.0
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 4)


def summarize(results):
    """(status, seconds) 목록 → 리포트용 요약.

    503 을 '실패'로 세면 안 된다. 그건 한도를 지키느라 **의도적으로** 거절한 것이고
    설계대로 동작하고 있다는 증거다. 진짜 문제는 5xx(500·502·504)와 타임아웃이다.
    """
    times = [t for _, t in results]
    ok = sum(1 for s, _ in results if 200 <= s < 400)
    rejected = sum(1 for s, _ in results if s in (429, 503))
    failed = sum(1 for s, _ in results
                 if (s >= 500 and s != 503) or s == TIMEOUT_STATUS)
    return {"total": len(results), "ok": ok, "rejected": rejected, "failed": failed,
            "p50": percentile(times, 50), "p95": percentile(times, 95),
            "max": round(max(times), 4) if times else 0.0}


async def visitor(client, base, deadline, results):
    """가상 관람객 한 명의 한 세션."""
    async def hit(method, path, **kw):
        t0 = time.monotonic()
        try:
            r = await client.request(method, base + path, **kw)
            results.append((r.status_code, time.monotonic() - t0))
        except Exception:                   # noqa: BLE001 - 타임아웃도 결과다
            results.append((TIMEOUT_STATUS, time.monotonic() - t0))

    await hit("POST", "/api/auth/login",
              json={"email": "senior@daon.com", "password": "pw"})
    await hit("GET", "/")                   # SPA index.html
    await hit("GET", "/api/auth/me")
    await hit("GET", "/api/survey/latest")
    await hit("GET", "/api/consulting/reports")
    # 실시간 화면에 머무는 동안의 상태 폴링 — 프런트가 1.5초마다 한다
    while time.monotonic() < deadline:
        await hit("GET", "/api/live/status")
        await asyncio.sleep(1.5 + random.random() * 0.5)


async def run(base, users, seconds, timeout):
    deadline = time.monotonic() + seconds
    results = []
    limits = httpx.Limits(max_connections=users * 2)
    async with httpx.AsyncClient(timeout=timeout, limits=limits,
                                 follow_redirects=True) as client:
        # 한꺼번에 붙이지 않고 조금씩 늘린다 — 실제 관람객도 동시에 도착하지 않고,
        # 동시 접속 순간만 재면 정상 운영 상태를 못 본다.
        tasks = []
        for _ in range(users):
            tasks.append(asyncio.create_task(visitor(client, base, deadline, results)))
            await asyncio.sleep(seconds / (users * 4))
        await asyncio.gather(*tasks, return_exceptions=True)
    return results


async def fetch_metrics(base):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(base + "/api/metrics")
            return r.json() if r.status_code == 200 else None
    except Exception:                       # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--slo", type=float, default=2.0,
                    help="p95 응답시간 상한(초). 넘으면 종료코드 1")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    print(f"가상 관람객 {args.users}명 / {args.seconds}초 → {base}")
    before = asyncio.run(fetch_metrics(base))
    results = asyncio.run(run(base, args.users, args.seconds, args.timeout))
    after = asyncio.run(fetch_metrics(base))

    s = summarize(results)
    print(f"\n요청 {s['total']}건 — 정상 {s['ok']} / 거절 {s['rejected']} / 실패 {s['failed']}")
    print(f"응답시간  p50 {s['p50']}s   p95 {s['p95']}s   최대 {s['max']}s")
    if after:
        print(f"서버 카운터: 요청 {after['requests']['total']}건, "
              f"느린요청 {after['slow_requests']}건, "
              f"분석대기 {after['jobs']['inflight']}/{after['jobs']['max_inflight']}, "
              f"체험세션 {after['live']['self_sessions']}/{after['live']['self_max']}")
        print(f"상태코드 분포: {after['requests']['by_status']}")
    elif before is None:
        print("(/api/metrics 를 못 읽었습니다 — 서버가 옛 버전이거나 접근이 막혀 있습니다)")

    bad = s["failed"] > 0 or s["p95"] > args.slo
    print("\n결과: " + ("문제 있음" if bad else "정상"))
    if s["failed"]:
        print(f"  · 실패(5xx·타임아웃) {s['failed']}건 — 서버 로그를 확인하세요")
    if s["p95"] > args.slo:
        print(f"  · p95 {s['p95']}s 가 기준 {args.slo}s 를 넘습니다")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
