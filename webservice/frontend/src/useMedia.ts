import { useEffect, useState } from "react";
import { MOBILE_MAX } from "./theme";

/**
 * 화면 폭이 모바일 범위인지. 768px 이하를 모바일로 본다.
 *
 * `window.innerWidth` 대신 `matchMedia` 를 쓰는 이유: 전시 사이트가 이 앱을
 * iframe 으로 임베드하므로, 브라우저 창이 아니라 **iframe 자체의 폭**을 기준으로
 * 반응해야 한다. matchMedia 는 문서 뷰포트(= iframe 폭)를 본다.
 */
export function useIsMobile(): boolean {
  const query = `(max-width: ${MOBILE_MAX}px)`;
  const [mobile, setMobile] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches,
  );

  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setMobile(e.matches);
    setMobile(mq.matches);
    // Safari 14 이하는 addEventListener 를 지원하지 않아 addListener 로 대체
    if (mq.addEventListener) {
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    }
    mq.addListener(onChange);
    return () => mq.removeListener(onChange);
  }, [query]);

  return mobile;
}
