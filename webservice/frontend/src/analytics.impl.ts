/**
 * 계측의 무거운 절반 — PostHog + Sentry 실물.
 *
 * **왜 파일이 둘로 나뉘어 있나.** 이 두 라이브러리를 합치면 gzip 기준 약 110KB 다.
 * 원래 번들이 gzip 70KB 남짓이었으니 그냥 임포트하면 첫 로딩이 세 배 가까이
 * 무거워진다 — 전시 관람객 상당수가 폰으로, 그것도 iframe 안에서 여는 앱에서는
 * 그대로 이탈로 돌아온다. 측정하려다 측정 대상을 망치는 셈이다.
 *
 * 그래서 이 파일은 `analytics.ts` 가 **동적 import 로** 불러온다. 별도 청크로
 * 빠지므로 첫 화면은 예전 크기 그대로 뜨고, 계측은 그 뒤에 따라붙는다.
 * 키가 설정돼 있지 않으면 이 청크는 아예 내려받지도 않는다.
 *
 * 이 파일을 어디서든 **정적으로 임포트하면 그 효과가 사라진다.** 번들러가
 * 메인 청크로 다시 끌어올린다. 진입점은 analytics.ts 하나뿐이어야 한다.
 */

import posthog from "posthog-js";
import * as Sentry from "@sentry/react";

import type { RuntimeConfig } from "./analytics";

let phReady = false;

export function setup(cfg: RuntimeConfig, inIframe: boolean): void {
  if (cfg.sentry_dsn) {
    try {
      Sentry.init({
        dsn: cfg.sentry_dsn,
        environment: cfg.environment || "production",
        release: cfg.release || undefined,
        // 전시 한 달 + 무료 티어. 에러는 다 받고 성능 트레이스는 표본만 받는다.
        tracesSampleRate: 0.1,
        // 세션 리플레이는 껐다. 관람객 화면을 그대로 녹화하는 기능이라 전시
        // 앱에서는 개인정보 부담이 크고, 무료 티어 한도도 빨리 닳는다.
        // 화면 흐름은 PostHog 퍼널로 충분히 본다.
        replaysSessionSampleRate: 0,
        replaysOnErrorSampleRate: 0,
        ignoreErrors: [
          // 확장 프로그램·번역기가 만드는 잡음. 우리 코드와 무관하다.
          "ResizeObserver loop limit exceeded",
          "ResizeObserver loop completed with undelivered notifications",
          // 관람객이 분석 도중 탭을 닫거나 폰이 절전으로 들어가면 이걸로 끊긴다.
          "AbortError",
          "NetworkError when attempting to fetch resource",
          "Failed to fetch",
          "Load failed",
        ],
      });
      Sentry.setTag("embedded", String(inIframe));
    } catch (err) {
      console.warn("[sentry] 초기화 실패", err);
    }
  }

  if (cfg.posthog_key) {
    try {
      posthog.init(cfg.posthog_key, {
        api_host: cfg.posthog_host || "https://us.i.posthog.com",
        // 임베드에서는 저장소를 못 쓴다(analytics.ts 상단 주석). 메모리로 내리면
        // 새로고침마다 새 사람으로 세지지만, 우리가 보려는 건 '한 방문 안에서
        // 어디까지 갔는가'라 퍼널 자체는 그대로 읽힌다.
        persistence: inIframe ? "memory" : "localStorage+cookie",
        // 자동 페이지뷰를 끈다. SPA 라 주소가 바뀌어도 페이지 로드가 없어서
        // 자동 수집은 첫 화면 하나만 잡는다. App.tsx 가 라우트마다 직접 보낸다.
        capture_pageview: false,
        // 클릭 자동 수집도 끈다. 이름 없는 이벤트가 수천 개 쌓이면 무료 티어
        // 이벤트 한도만 먹고 퍼널은 오히려 읽기 어려워진다.
        autocapture: false,
        // 관람객 IP 를 저장하지 않는다. 전시에 필요한 정보가 아니다.
        ip: false,
        loaded: () => { phReady = true; },
      });
      posthog.register({ embedded: inIframe });
    } catch (err) {
      console.warn("[posthog] 초기화 실패", err);
    }
  }
}

export function capture(event: string, props?: Record<string, unknown>): void {
  if (!phReady) return;
  try {
    posthog.capture(event, props);
  } catch {
    // 삼킨다 — 통계 때문에 화면이 죽으면 안 된다
  }
}

export function captureError(err: unknown, context?: Record<string, unknown>): void {
  try {
    Sentry.captureException(err, context ? { extra: context } : undefined);
  } catch { /* 삼킨다 */ }
}
