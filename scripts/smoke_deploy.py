#!/usr/bin/env python3
"""배포된 URL을 상대로 제출 전 점검(작업 H)을 자동으로 돌린다.

    python3 scripts/smoke_deploy.py https://내주소.example.com
    python3 scripts/smoke_deploy.py http://localhost:8000 --local

체크리스트를 사람이 손으로 훑으면 재배포할 때마다 다시 훑어야 하고, 빠뜨린
항목은 조용히 넘어간다. 여기 있는 것은 전부 프로그램이 판정할 수 있는 항목이다.
사람 눈이 필요한 것(모바일 실기기, 화면이 예쁜지)은 마지막에 목록으로 남긴다.

종료 코드: 실패가 하나라도 있으면 1.
"""

import argparse
import concurrent.futures
import io
import sys
import time

try:
    import httpx
except ImportError:
    sys.exit("httpx 가 필요합니다:  pip install httpx")

OK, FAIL, WARN, SKIP = "✅", "❌", "⚠️ ", "⏭️ "
_results = []


def check(name, condition, detail="", warn_only=False):
    mark = OK if condition else (WARN if warn_only else FAIL)
    _results.append((mark, name))
    print(f"{mark} {name}" + (f"  — {detail}" if detail else ""))
    return condition


def skip(name, why):
    _results.append((SKIP, name))
    print(f"{SKIP} {name}  — {why}")


def section(title):
    print(f"\n\033[1m{title}\033[0m")


# --------------------------------------------------------------------------

def check_transport(base, client, local):
    section("배포")
    if local:
        skip("HTTPS 로 열림", "--local 모드")
    else:
        check("HTTPS 로 열림", base.startswith("https://"),
              "전시 사이트가 HTTPS 페이지라 HTTP 는 iframe 에서 차단된다")

    try:
        r = client.get(f"{base}/api/health", timeout=15)
    except Exception as exc:
        check("서버 응답", False, f"{type(exc).__name__}: {exc}")
        return False
    check("서버 응답", r.status_code == 200 and r.json().get("status") == "ok",
          f"HTTP {r.status_code}")

    csp = r.headers.get("content-security-policy", "")
    check("CSP frame-ancestors 설정됨", "frame-ancestors" in csp, csp or "없음")
    check("X-Frame-Options 없음",
          "x-frame-options" not in {k.lower() for k in r.headers},
          "값이 있으면 iframe 이 무조건 막힌다")
    return True


def check_spa(base, client):
    r = client.get(f"{base}/", timeout=15)
    check("SPA 진입 페이지", r.status_code == 200 and '<div id="root"' in r.text)
    check("index.html 캐시 금지",
          "no-cache" in r.headers.get("cache-control", ""),
          r.headers.get("cache-control", "없음") + " — 새 배포가 옛 화면으로 보인다",
          warn_only=True)
    deep = client.get(f"{base}/live", timeout=15)
    check("새로고침해도 라우팅 유지 (/live)",
          deep.status_code == 200 and '<div id="root"' in deep.text)


def check_session(base, client, email, password, local):
    section("세션 · 인증")
    r = client.post(f"{base}/api/auth/login",
                    json={"email": email, "password": password}, timeout=15)
    if not check("로그인", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}"):
        return False

    cookie = r.headers.get("set-cookie", "")
    if local:
        skip("쿠키 SameSite=None; Secure", "--local 모드 (HTTP 라 Secure 불가)")
    else:
        check("쿠키 SameSite=None; Secure",
              "samesite=none" in cookie.lower() and "secure" in cookie.lower(),
              "iframe 안에서 로그인이 유지되려면 둘 다 필요하다 (DAON_EMBED=1)")

    me = client.get(f"{base}/api/auth/me", timeout=15)
    check("세션 유지 (재요청에도 로그인 상태)", me.status_code == 200)
    return True


def _sample_bytes(base, client, path):
    """진짜 영상일 때만 바이트를 돌려준다.

    SPA 폴백이 없는 경로에도 index.html 을 200 으로 돌려주므로 상태코드만으로는
    파일이 있는지 알 수 없다 — content-type 까지 봐야 한다.
    """
    r = client.get(f"{base}{path}", timeout=60)
    ctype = r.headers.get("content-type", "")
    if r.status_code != 200 or not ctype.startswith("video"):
        return None
    return r.content


def check_samples(base, client):
    section("체험 콘텐츠")
    found = {}
    for name in ("bedroom", "living", "kitchen"):
        data = _sample_bytes(base, client, f"/samples/{name}.mp4")
        if data:
            found[name] = data
        check(f"샘플 영상 {name}.mp4", bool(data),
              f"{len(data)//1024}KB" if data else "아직 없음 (SPA 폴백)",
              warn_only=not data)
    demo = client.get(f"{base}/demo/fall-detection-demo.mp4", timeout=60)
    check("실시간 데모 영상",
          demo.status_code == 200 and
          demo.headers.get("content-type", "").startswith("video"),
          "없으면 /live 가 '준비 중' 안내로 대체된다", warn_only=True)
    return found


def _analyze(base, client, blob, filename, location="거실", timeout=120):
    """업로드 → 폴링 → (걸린 초, 상태, 리포트 id). 프런트와 같은 흐름."""
    t0 = time.perf_counter()
    r = client.post(f"{base}/api/consulting/analyze",
                    files={"file": (filename, io.BytesIO(blob), "video/mp4")},
                    data={"location": location}, timeout=timeout)
    if r.status_code != 200:
        return time.perf_counter() - t0, f"HTTP {r.status_code}", None
    job = r.json()["job_id"]
    while time.perf_counter() - t0 < timeout:
        st = client.get(f"{base}/api/consulting/status/{job}", timeout=15).json()
        if st["status"] in ("done", "error"):
            return time.perf_counter() - t0, st["status"], st.get("report_id")
        time.sleep(0.5)
    return time.perf_counter() - t0, "timeout", None


def check_cache(base, client, samples):
    section("캐시 · 리포트")
    if not samples:
        skip("샘플 업로드가 캐시로 즉시 응답", "샘플 영상이 아직 없음")
        skip("리포트 이미지 렌더링", "샘플 영상이 아직 없음")
        return
    name, blob = next(iter(samples.items()))
    elapsed, status, rid = _analyze(base, client, blob, f"{name}.mp4")
    check("샘플 업로드가 완료됨", status == "done", f"{status} · {elapsed:.1f}초")
    check("캐시로 즉시 응답 (2초 이내)", status == "done" and elapsed < 2.0,
          f"{elapsed:.1f}초 — 느리면 build_samples.py 를 안 돌렸거나 해시가 바뀐 것",
          warn_only=True)
    if rid:
        rep = client.get(f"{base}/api/consulting/report/{rid}", timeout=15).json()
        check("리포트 본문", bool(rep.get("summary")) and bool(rep.get("findings")))
        img = client.get(f"{base}/api/consulting/report/{rid}/image", timeout=30)
        check("리포트 이미지(경로+위험구간) 렌더링",
              img.status_code == 200 and len(img.content) > 1000,
              f"{len(img.content)} bytes")


def check_limits(base, client, limit_mb, skip_big):
    section("부하 방어")

    empty = client.post(f"{base}/api/consulting/analyze",
                        files={"file": ("empty.mp4", b"", "video/mp4")}, timeout=30)
    check("빈 파일 거절", empty.status_code == 400, f"HTTP {empty.status_code}")

    if skip_big:
        skip("업로드 크기 제한이 실제로 걸림", "--skip-big-upload")
        return
    # 상한을 조금 넘기는 크기. 서버는 한도를 넘는 순간 연결을 끊으므로
    # 이 바이트가 전부 올라가지는 않는다.
    big = b"\0" * int((limit_mb + 10) * 1024 * 1024)
    try:
        r = client.post(f"{base}/api/consulting/analyze",
                        files={"file": ("big.mp4", io.BytesIO(big), "video/mp4")},
                        timeout=300)
        check("업로드 크기 제한이 실제로 걸림", r.status_code == 413,
              f"HTTP {r.status_code}")
        if r.status_code == 413:
            check("크기 초과 안내가 사람이 읽을 문장", "MB" in r.json().get("detail", ""),
                  r.json().get("detail", "")[:80])
    except Exception as exc:
        check("업로드 크기 제한이 실제로 걸림", False, f"{type(exc).__name__}: {exc}")


def check_concurrency(base, client, samples, n):
    section(f"동시 요청 {n}개")
    blob = next(iter(samples.values())) if samples else b"not-a-real-video" * 999

    def one(i):
        # 스레드마다 클라이언트를 따로 둔다. 쿠키만 복사해 같은 세션으로 붙는다.
        with httpx.Client(follow_redirects=True) as c:
            c.cookies.update(client.cookies)
            return _analyze(base, c, blob, f"load{i}.mp4", timeout=90)

    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        out = list(pool.map(one, range(n)))
    wall = time.perf_counter() - t0

    statuses = [s for _, s, _ in out]
    done = statuses.count("done")
    busy = sum(1 for s in statuses if s == "HTTP 503")
    other5xx = [s for s in statuses if s.startswith("HTTP 5") and s != "HTTP 503"]

    check("동시 요청 뒤에도 서버가 살아 있음",
          client.get(f"{base}/api/health", timeout=15).status_code == 200)
    check("예상 못 한 5xx 없음", not other5xx, ", ".join(other5xx) or "없음")
    print(f"   완료 {done} · 혼잡거절(503) {busy} · 기타 {n - done - busy}"
          f" · 총 {wall:.1f}초")
    if busy:
        print("   (503 은 정상 동작이다 — 무한 대기 대신 거절하도록 만든 값)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="예: https://daon.example.com")
    ap.add_argument("--email", default="senior@daon.com")
    ap.add_argument("--password", default="pw")
    ap.add_argument("--local", action="store_true",
                    help="HTTPS·Secure 쿠키 검사를 건너뛴다")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--limit-mb", type=float, default=200,
                    help="서버의 업로드 상한(DAON_MAX_UPLOAD_MB). 여기에 10MB 를 "
                         "더한 파일을 보내 413 이 걸리는지 본다")
    ap.add_argument("--skip-big-upload", action="store_true",
                    help="큰 업로드 검사를 건너뛴다(느린 회선)")
    args = ap.parse_args()

    base = args.url.rstrip("/")
    print(f"\033[1m다온 배포 점검\033[0m  →  {base}")

    with httpx.Client(follow_redirects=True) as client:
        if not check_transport(base, client, args.local):
            sys.exit(1)
        check_spa(base, client)
        if check_session(base, client, args.email, args.password, args.local):
            samples = check_samples(base, client)
            check_cache(base, client, samples)
            check_limits(base, client, args.limit_mb, args.skip_big_upload)
            check_concurrency(base, client, samples, args.concurrency)

    fails = [n for m, n in _results if m == FAIL]
    warns = [n for m, n in _results if m == WARN]
    print(f"\n\033[1m결과\033[0m  통과 {sum(1 for m, _ in _results if m == OK)} · "
          f"경고 {len(warns)} · 실패 {len(fails)} · "
          f"건너뜀 {sum(1 for m, _ in _results if m == SKIP)}")
    for n in fails:
        print(f"  {FAIL} {n}")

    print("\n\033[1m사람이 직접 봐야 하는 것\033[0m")
    for line in ("전시 사이트와 같은 구조의 페이지에 iframe 으로 넣고 전체 플로우",
                 "iOS Safari · Android Chrome 실기기에서 레이아웃과 영상 재생",
                 "서버를 재시작한 뒤 지난 리포트가 그대로 남아 있는지(볼륨 연결)"):
        print(f"  □ {line}")

    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
