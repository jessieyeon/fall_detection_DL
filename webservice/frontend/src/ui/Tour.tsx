import { useEffect, useLayoutEffect, useState } from "react";
import { color, font, radius, shadow } from "../theme";
import Button from "./Button";

/**
 * 첫 방문 온보딩 투어.
 *
 * 1단계는 화면 중앙의 환영 팝업, 이후 단계는 실제 UI 요소에 스포트라이트를
 * 비추고 나머지를 어둡게 가린 뒤 옆에 말풍선으로 설명한다. 게임 튜토리얼처럼
 * '어디를 누르면 무엇이 나오는지'를 화면 위에서 직접 가리키기 위해서다.
 *
 * 대상 요소는 `data-tour="..."` 속성으로 찾는다. 컴포넌트 참조를 넘기는 것보다
 * 페이지 구조가 바뀌어도 투어가 덜 깨지고, 대상이 없으면 그 단계를 건너뛴다.
 */

type Step = {
  /** data-tour 속성값. 없으면 중앙 팝업 */
  target?: string;
  title: string;
  body: string;
};

const STEPS: Step[] = [
  {
    title: "다온 안전지킴이 체험에 오신 것을 환영합니다",
    body: "다온 안전지킴이는 어르신의 안전한 일상을 위해 컨설팅과 실시간 감지를 "
      + "제공하는 보호자용 앱입니다. 멀리 떨어져 있어도 어르신 곁의 위험을 "
      + "확인하고 대비할 수 있어요. 주요 기능을 잠깐 안내해드릴게요.",
  },
  {
    target: "nav-consult",
    title: "컨설팅",
    body: "생활 영상을 올려주시면 동선을 분석해 안전 타일이 어디에 필요한지 "
      + "알려드립니다. 지금 보고 계신 화면이에요.",
  },
  {
    target: "samples",
    title: "체험용 영상으로 바로 분석",
    body: "생활 영상은 실제 카메라 설치가 필요해서, 체험용으로 미리 준비된 "
      + "영상을 눌러 분석 결과를 바로 볼 수 있게 했어요.",
  },
  {
    target: "nav-monitor",
    title: "실시간",
    body: "카메라를 연결하면 AI가 인식한 자세(스켈레톤)를 실시간으로 볼 수 "
      + "있습니다. 카메라가 준비되지 않았다면 데모 영상으로 확인해주세요.",
  },
];

const PAD = 8;          // 스포트라이트가 대상보다 살짝 크게 뚫리는 여유
const GAP = 14;         // 대상과 말풍선 사이 간격

export default function Tour({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const cur = STEPS[step];
  const last = step === STEPS.length - 1;

  // 대상 위치 측정. 스크롤·리사이즈에도 따라가야 스포트라이트가 어긋나지 않는다.
  useLayoutEffect(() => {
    if (!cur.target) { setRect(null); return; }
    const el = document.querySelector<HTMLElement>(`[data-tour="${cur.target}"]`);
    if (!el) {
      // 대상이 없는 단계(레이아웃 변경 등)는 조용히 건너뛴다
      setStep((s) => (s + 1 < STEPS.length ? s + 1 : s));
      return;
    }
    el.scrollIntoView({ block: "nearest", behavior: "instant" as ScrollBehavior });
    const measure = () => setRect(el.getBoundingClientRect());
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [step, cur.target]);

  // 투어 중 배경 스크롤 잠금
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  const next = () => (last ? onClose() : setStep(step + 1));

  // ── 환영 팝업 (대상 없음) ──────────────────────────────────────────────
  if (!cur.target || !rect) {
    return (
      <div style={{
        position: "fixed", inset: 0, zIndex: 100,
        background: "rgba(16,22,35,0.62)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}>
        <div style={{
          width: "100%", maxWidth: 400, background: color.surface,
          borderRadius: radius.lg, boxShadow: shadow.raised,
          padding: 24, display: "flex", flexDirection: "column", gap: 14,
        }}>
          <div style={{ fontSize: font.h2, fontWeight: 700, lineHeight: 1.4 }}>
            {cur.title}
          </div>
          <p style={{ margin: 0, fontSize: font.small, color: color.inkSoft, lineHeight: 1.7 }}>
            {cur.body}
          </p>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <button onClick={onClose} style={{ fontSize: font.caption, color: color.inkFaint }}>
              건너뛰기
            </button>
            <Button onClick={next}>다음</Button>
          </div>
        </div>
      </div>
    );
  }

  // ── 스포트라이트 단계 ──────────────────────────────────────────────────
  const hole = {
    left: rect.left - PAD,
    top: rect.top - PAD,
    width: rect.width + PAD * 2,
    height: rect.height + PAD * 2,
  };
  // 말풍선은 대상이 화면 아래쪽이면 위에, 위쪽이면 아래에 둔다
  const below = rect.top < window.innerHeight / 2;
  const tipStyle: React.CSSProperties = below
    ? { top: hole.top + hole.height + GAP }
    : { bottom: window.innerHeight - hole.top + GAP };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 100 }}>
      {/* 구멍 뚫린 어두운 배경: 대상 크기의 투명 박스에 거대한 그림자를 둘러
          나머지 화면 전체를 가린다. 클릭도 여기서 막는다. */}
      <div onClick={next} style={{ position: "fixed", inset: 0 }} />
      <div style={{
        position: "fixed", ...hole,
        borderRadius: radius.md,
        boxShadow: "0 0 0 9999px rgba(16,22,35,0.62)",
        border: `2px solid ${color.brand}`,
        pointerEvents: "none",
        transition: "all .25s ease",
      }} />

      <div style={{
        position: "fixed", left: 16, right: 16, ...tipStyle,
        maxWidth: 420, margin: "0 auto",
        background: color.surface, borderRadius: radius.lg,
        boxShadow: shadow.raised, padding: 18,
        display: "flex", flexDirection: "column", gap: 10,
      }}>
        <div style={{ fontSize: font.body, fontWeight: 700 }}>{cur.title}</div>
        <p style={{ margin: 0, fontSize: font.small, color: color.inkSoft, lineHeight: 1.65 }}>
          {cur.body}
        </p>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <span style={{ fontSize: font.caption, color: color.inkFaint }}>
            {step} / {STEPS.length - 1}
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onClose} style={{ fontSize: font.caption, color: color.inkFaint }}>
              건너뛰기
            </button>
            <Button onClick={next}>{last ? "시작하기" : "다음"}</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
