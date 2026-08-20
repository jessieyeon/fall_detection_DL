/**
 * 계측 진입점 — 앱의 나머지는 전부 이 파일만 임포트한다.
 *
 * 실제 SDK(PostHog, Sentry)는 `analytics.impl.ts` 에 있고 동적으로 불러온다.
 * 이유는 그 파일 상단에 적어두었다(요약: 두 SDK 를 메인 번들에 넣으면 첫 로딩이
 * 세 배가 되어, 측정하려던 이탈을 측정 도구가 만들어낸다).
 *
 * 설계 원칙 하나: **계측이 앱을 망가뜨리면 안 된다.** 관람객이 보는 화면이
 * 통계 스크립트 때문에 안 뜨는 것보다, 통계가 없는 게 백 번 낫다. 모든 경로에서
 * 예외를 삼키고, 초기화 실패는 콘솔 경고로만 남긴다.
 *
 * 원칙 둘: **iframe 안에서 돌아야 한다.** 전시 사이트가 우리를 임베드하므로
 * 우리 저장소는 서드파티 저장소가 된다(storage.ts 주석 참고). PostHog 의 기본
 * 저장 방식은 쿠키 + localStorage 인데, 서드파티 컨텍스트에서 쿠키는 SameSite
 * 때문에 버려지고 localStorage 는 브라우저에 따라 접근만 해도 SecurityError 를
 * 던진다. → 임베드일 때는 메모리 저장으로 내린다(impl 쪽에서 처리).
 */

export interface RuntimeConfig {
  posthog_key: string;
  posthog_host: string;
  sentry_dsn: string;
  environment: string;
  release: string;
}

type Impl = typeof import("./analytics.impl");

let impl: Impl | null = null;

/**
 * SDK 가 준비되기 전에 발생한 이벤트를 잠깐 담아둔다.
 *
 * 설정을 받아오는 데 몇백 ms 가 걸리는데, 그 사이에 이미 첫 페이지뷰가 난다.
 * 그걸 버리면 퍼널의 분모(=앱을 연 사람)가 통째로 비어 모든 전환율이
 * 100% 처럼 보인다 — 없는 것보다 나쁜 숫자다.
 *
 * 상한을 두는 이유: 설정을 영영 못 받는 환경(사내망 차단 등)에서 배열이
 * 무한정 자라지 않게 한다.
 */
const pending: Array<(m: Impl) => void> = [];
const MAX_PENDING = 50;

function run(fn: (m: Impl) => void): void {
  if (impl) {
    fn(impl);
  } else if (pending.length < MAX_PENDING) {
    pending.push(fn);
  }
}

/** iframe 안에서 뜨고 있나. 저장 방식과 이벤트 속성 양쪽에서 쓴다. */
function embedded(): boolean {
  try {
    return window.self !== window.top;
  } catch {
    // 크로스 오리진이면 접근 자체가 막힌다 — 막혔다는 건 임베드라는 뜻이다.
    return true;
  }
}

/**
 * 서버에서 키를 받아 초기화한다. main.tsx 가 한 번 부른다.
 *
 * 키를 빌드에 박지 않고 런타임에 받는 이유는 app.py 의 `/api/config` 주석에
 * 적어두었다(요약: Vite 는 빌드 시점에 값을 박으므로, Docker 빌드에 환경변수를
 * 따로 넘기지 않으면 조용히 빈 값이 들어간다).
 *
 * 트레이드오프: 설정이 도착하기 전 몇백 ms 사이에 난 **에러**는 Sentry 가 놓친다
 * (이벤트는 위 큐가 받아준다). 그 구간의 서버 측 에러는 백엔드 Sentry 가 잡으므로
 * 감수할 만하다고 봤다.
 */
export async function initAnalytics(): Promise<void> {
  let cfg: RuntimeConfig;
  try {
    const res = await fetch("/api/config", { credentials: "include" });
    if (!res.ok) return;
    cfg = (await res.json()) as RuntimeConfig;
  } catch {
    return;                          // 설정을 못 받으면 계측 없이 그냥 뜬다
  }

  // 둘 다 꺼져 있으면 무거운 청크를 내려받을 이유가 없다. 로컬 개발이 여기 해당한다.
  if (!cfg.posthog_key && !cfg.sentry_dsn) return;

  try {
    const m = await import("./analytics.impl");
    m.setup(cfg, embedded());
    impl = m;
    // splice 로 비우면서 꺼낸다 — 플러시 도중 들어온 이벤트는 impl 이 이미
    // 채워져 있으므로 큐를 거치지 않고 바로 나간다.
    for (const fn of pending.splice(0)) {
      try { fn(m); } catch { /* 한 건 실패가 나머지를 막지 않게 */ }
    }
  } catch (err) {
    console.warn("[analytics] 불러오기 실패", err);
  }
}

/** 퍼널 이벤트 한 건. 이름은 아래 EVENTS 에서 고른다. */
export function track(event: string, props?: Record<string, unknown>): void {
  run((m) => m.capture(event, props));
}

/** 라우트가 바뀔 때마다. App.tsx 가 부른다. */
export function trackPageview(path: string): void {
  run((m) => m.capture("$pageview", { $current_url: path, path }));
}

/**
 * 잡아서 처리한 에러를 Sentry 로 보낸다.
 *
 * try/catch 로 이미 화면에 안내를 띄운 실패는 window.onerror 를 타지 않아
 * Sentry 가 모른다 — 우리 앱에서 제일 아픈 실패(영상 분석 실패)가 정확히
 * 그 모양이라 직접 보내야 한다.
 */
export function reportError(err: unknown, context?: Record<string, unknown>): void {
  run((m) => m.captureError(err, context));
}

/**
 * 이벤트 이름 상수.
 *
 * 문자열을 여기저기 직접 쓰면 오타 하나로 퍼널이 끊긴다 — 그런데 PostHog 는
 * 오타 난 이름도 얌전히 받아주기 때문에 대시보드를 열어보기 전까지 모른다.
 * 순서는 관람객이 실제로 지나가는 순서와 같게 유지할 것.
 */
export const EVENTS = {
  APP_OPEN: "app_opened",            // 앱이 떴다 (퍼널의 분모)
  GUEST_START: "guest_started",      // '체험하기' 를 눌렀다
  LOGIN: "logged_in",                // 계정으로 로그인했다
  LOGIN_FAILED: "login_failed",
  TOUR_SHOWN: "tour_shown",          // 온보딩 안내가 떴다
  TOUR_DONE: "tour_finished",        // 끝까지 봤거나 닫았다
  ANALYZE_START: "analyze_started",  // 영상을 올렸다 ← 여기가 진짜 첫 경험
  ANALYZE_DONE: "analyze_finished",  // 리포트가 나왔다
  ANALYZE_FAILED: "analyze_failed",
  LIVE_OPEN: "live_opened",          // 실시간(AI 세션) 화면에 들어왔다
} as const;
