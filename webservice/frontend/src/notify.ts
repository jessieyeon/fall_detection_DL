/**
 * 분석 완료 알림.
 *
 * 사용자가 다른 탭·다른 앱에 가 있어도 결과가 나온 걸 알 수 있어야 한다.
 * 세 겹으로 처리한다.
 *
 *  1. 시스템 알림(Notification API) — 브라우저 밖에서도 뜬다. 가장 좋지만
 *     권한이 필요하고, **전시 사이트가 우리를 iframe 으로 넣으면 막힐 수 있다.**
 *     교차 출처 iframe 에서 Notification 권한 요청은 기본적으로 거부되며,
 *     부모가 `allow="notifications"` 를 붙여야 열린다. 우리가 통제할 수 없다.
 *  2. 탭 제목 깜빡임 — 권한이 없어도 동작한다. 다른 탭에 있으면 이걸로 알아챈다.
 *  3. 화면 안 배너 — 호출부가 직접 렌더링한다. 위 둘이 다 막혀도 남는 최후 수단.
 *
 * 그래서 1이 실패해도 조용히 넘어가고 2로 대체한다. 알림이 안 뜬다고 기능이
 * 멈추면 안 된다.
 */

let titleTimer: ReturnType<typeof setInterval> | null = null;
let originalTitle = "";

/** 권한을 미리 물어둔다. 사용자 제스처(업로드 클릭) 안에서 불러야 한다. */
export async function primeNotifications(): Promise<void> {
  try {
    if (typeof Notification === "undefined") return;
    if (Notification.permission === "default") await Notification.requestPermission();
  } catch {
    // iframe·비보안 컨텍스트에서 던질 수 있다. 무시하고 제목 깜빡임으로 간다.
  }
}

function flashTitle(message: string) {
  stopTitleFlash();
  originalTitle = document.title;
  let on = false;
  titleTimer = setInterval(() => {
    document.title = on ? originalTitle : message;
    on = !on;
  }, 900);

  const stop = () => {
    if (!document.hidden) {
      stopTitleFlash();
      document.removeEventListener("visibilitychange", stop);
    }
  };
  document.addEventListener("visibilitychange", stop);
}

export function stopTitleFlash() {
  if (titleTimer) {
    clearInterval(titleTimer);
    titleTimer = null;
    if (originalTitle) document.title = originalTitle;
  }
}

/** 분석 완료를 알린다. 화면을 보고 있으면 굳이 방해하지 않는다. */
export function notifyDone(title: string, body: string) {
  if (!document.hidden) return;      // 이미 보고 있으면 알림 불필요

  flashTitle(`✅ ${title}`);

  try {
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      const n = new Notification(title, { body, tag: "daon-analysis", icon: "/favicon.ico" });
      n.onclick = () => { window.focus(); stopTitleFlash(); n.close(); };
    }
  } catch {
    // 제목 깜빡임으로 충분하다
  }
}
