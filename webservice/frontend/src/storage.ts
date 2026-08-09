/**
 * localStorage 안전 래퍼.
 *
 * 전시 사이트가 우리를 iframe 으로 임베드하면 우리 저장소는 '서드파티 저장소'가
 * 된다. Safari 의 추적 방지(ITP)나 사용자의 쿠키 차단 설정에서는 `localStorage`
 * 에 접근하는 것만으로 SecurityError 가 던져진다. 시크릿 모드에서 용량이 0인
 * 경우도 있다.
 *
 * 저장이 안 되는 것 자체는 큰 문제가 아니다(안내를 한 번 더 보는 정도).
 * 하지만 예외가 그대로 올라가면 화면이 통째로 안 뜬다. 그래서 전부 삼키고,
 * 실패하면 메모리에만 기억한다 — 같은 세션 안에서는 정상 동작한다.
 */

// 앱 안내를 봤는지 표시하는 키. App(표시 판단)과 Login(체험 진입 시 초기화)이
// 함께 쓰므로 여기 둔다 — Login 이 App 을 임포트하면 순환이 생긴다.
export const TOUR_SEEN = "daon.tour.seen";

const memory = new Map<string, string>();

export function getFlag(key: string): string | null {
  try {
    const v = window.localStorage.getItem(key);
    if (v !== null) return v;
  } catch {
    // 접근 자체가 막힌 환경 — 메모리로 대체
  }
  return memory.get(key) ?? null;
}

export function setFlag(key: string, value: string): void {
  memory.set(key, value);
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // 저장 실패는 무시. 이번 세션 동안은 메모리 값이 쓰인다.
  }
}
