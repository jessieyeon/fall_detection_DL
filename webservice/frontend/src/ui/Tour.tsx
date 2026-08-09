import { useEffect, useLayoutEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { color, font, radius, shadow } from "../theme";
import { Chevron } from "./icons";
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

/**
 * 안내는 짧게, 눈으로 훑어지게 쓴다.
 *
 * 예전에는 단계마다 서너 줄짜리 문단이었다. 관람객은 그걸 읽지 않고 '다음'을
 * 눌러버려서, 안내가 있으나 마나였다. 그래서 한 단계를 **한 줄 요약 + 짧은
 * 항목 두세 개**로 쪼갰다. 항목의 앞머리(굵은 글씨)만 읽어도 뜻이 통해야 한다.
 */
type Step = {
  /** data-tour 속성값. 없으면 중앙 팝업 */
  target?: string;
  /** 이 단계에서 배경에 띄울 화면. 설명하는 탭을 실제로 보여준다. */
  route: string;
  title: string;
  /** 제목 아래 한 줄 요약 */
  lead: string;
  /** [앞머리, 설명] 목록. 앞머리는 굵게 나온다. 첫 인사말처럼 나눌 것이
   *  없는 단계는 비운다. */
  points?: [string, string][];
};

/**
 * 순서가 마이페이지 → 실시간 → 컨설팅인 이유.
 *
 * 쓰는 순서대로 놓았다. 카메라와 어르신을 먼저 등록해야(마이페이지) 실시간
 * 감지가 의미가 있고, 그렇게 며칠 쌓인 영상을 돌려보는 것이 컨설팅이다.
 * 마지막을 컨설팅으로 두면 투어가 끝나는 자리가 기본 화면과도 맞는다.
 */
const STEPS: Step[] = [
  {
    route: "/mypage",
    title: "다온 안전지킴이",
    lead: "다온앱에 오신 것을 환영합니다.\n"
        + "지금부터 다온의 주요 기능을 간단히 소개해 드릴게요.",
  },
  {
    target: "nav-mypage",
    route: "/mypage",
    title: "마이페이지",
    lead: "119 신고를 도우려면 이 정보가 필요합니다.",
    points: [
      ["나의 카메라", "설치한 카메라를 등록하고 연결 상태를 봅니다"],
      ["어르신 정보", "이름·호실·주소를 넣어두면 신고 때 바로 읽어드립니다"],
    ],
  },
  {
    target: "nav-monitor",
    route: "/live",
    title: "실시간",
    lead: "카메라가 인식한 자세를 실시간으로 보여드립니다.",
    points: [
      // 0.4초는 자체 평가에서 관측된 최소 리드타임이다(평균은 더 길다).
      // 과장하지 않으려고 평균 대신 이 값을 쓴다 — 서보가 덮개를 여는 데
      // 0.15~0.3초라 0.4초면 타일이 먼저 펴진다.
      ["낙상 감지", "넘어지기 최소 0.4초 전에 알아채 타일을 폅니다"],
      ["카메라가 없다면", "이 기기 카메라나 데모 영상으로 체험해 보세요"],
    ],
  },
  {
    target: "nav-consult",
    route: "/consulting",
    title: "컨설팅",
    lead: "영상 속 동선을 분석해 안전 타일이 필요한 곳을 알려드립니다.",
    points: [
      ["체험용 영상", "미리 준비된 영상으로 바로 결과를 볼 수 있어요"],
      ["내 영상 올리기", "직접 찍은 영상도 분석할 수 있어요"],
    ],
  },
];

const PAD = 8;          // 스포트라이트가 대상보다 살짝 크게 뚫리는 여유
const GAP = 14;         // 대상과 말풍선 사이 간격

export default function Tour({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const cur = STEPS[step];
  const last = step === STEPS.length - 1;
  const nav = useNavigate();
  const here = useLocation().pathname;
  // 투어를 열기 전에 보고 있던 화면. '건너뛰기'는 여기로 되돌려 놓는다 —
  // 안내를 안 보겠다고 했는데 엉뚱한 탭에 남겨두면 더 헷갈린다.
  const [origin] = useState(here);
  const skip = () => { nav(origin, { replace: true }); onClose(); };

  /** 설명 중인 탭을 배경에 실제로 띄운다. 예전에는 어느 단계에서나 배경이
   *  컨설팅 화면이라, '마이페이지' 설명을 읽으면서 컨설팅을 보고 있었다.
   *  replace 를 쓰는 이유: 투어가 브라우저 뒤로가기 기록을 채우면 투어를
   *  끝낸 뒤 뒤로가기가 여러 번 눌려야 원래 자리로 돌아간다. */
  useLayoutEffect(() => {
    if (here !== cur.route) nav(cur.route, { replace: true });
  }, [step, cur.route, here, nav]);

  // 대상 위치 측정. 스크롤·리사이즈에도 따라가야 스포트라이트가 어긋나지 않는다.
  useLayoutEffect(() => {
    if (!cur.target) { setRect(null); return; }
    // 아직 그 화면으로 옮겨가는 중이면 대상이 없는 게 정상이다. 다음 렌더에서
    // 다시 잰다(여기서 건너뛰면 이동 중이라는 이유로 단계가 통째로 날아간다).
    if (here !== cur.route) return;
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
  }, [step, cur.target, cur.route, here]);

  // 투어 중 배경 스크롤 잠금
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  const next = () => (last ? onClose() : setStep(step + 1));
  const prev = () => setStep((s) => Math.max(0, s - 1));

  /** 제목·요약·항목 목록. 중앙 정렬로 놓는다 — 짧은 문장 몇 줄이라
   *  왼쪽 정렬보다 가운데가 카드 안에서 안정적으로 보인다. */
  const body = (
    <>
      <div style={{ fontSize: font.h2, fontWeight: 700, lineHeight: 1.4 }}>
        {cur.title}
      </div>
      {/* 줄바꿈은 원문 그대로 살린다(인사말이 네 줄로 쓰여 있다) */}
      <p style={{
        margin: 0, fontSize: font.small, color: color.inkSoft,
        lineHeight: 1.7, whiteSpace: "pre-line",
      }}>
        {cur.lead}
      </p>
      {cur.points && (
        <div style={{
          display: "flex", flexDirection: "column", gap: 7,
          padding: "12px 14px", borderRadius: radius.md, background: color.bg,
          textAlign: "left",    // 목록은 왼쪽 정렬 — 앞머리가 세로로 줄 맞는다
        }}>
          {cur.points.map(([head, desc]) => (
            <div key={head} style={{ fontSize: font.small, lineHeight: 1.55 }}>
              <b style={{ color: color.ink }}>{head}</b>
              <span style={{ color: color.inkSoft }}>: {desc}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );

  const footer = (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8,
    }}>
      {/* 첫 단계에서도 자리를 비워두지 않고 흐린 '<' 를 남긴다. 버튼이
          사라졌다 나타나면 옆의 페이지 표시가 좌우로 흔들린다. */}
      <button onClick={prev} disabled={step === 0} aria-label="이전"
              style={{
                width: 26, height: 26, flexShrink: 0, borderRadius: radius.sm,
                display: "flex", alignItems: "center", justifyContent: "center",
                color: step === 0 ? color.line : color.inkSoft,
                cursor: step === 0 ? "default" : "pointer",
              }}>
        <span style={{ display: "inline-flex", transform: "rotate(180deg)" }}>
          <Chevron size={15} color={step === 0 ? color.line : color.inkSoft} />
        </span>
      </button>
      <span style={{ fontSize: font.caption, color: color.inkFaint }}>
        {step + 1} / {STEPS.length}
      </span>
      <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
        <button onClick={skip} style={{ fontSize: font.caption, color: color.inkFaint }}>
          건너뛰기
        </button>
        <Button onClick={next}>{last ? "시작하기" : "다음"}</Button>
      </div>
    </div>
  );

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
          width: "100%", maxWidth: 420, background: color.surface,
          borderRadius: radius.lg, boxShadow: shadow.raised,
          padding: 24, display: "flex", flexDirection: "column", gap: 14,
          textAlign: "center",
        }}>
          {body}
          {footer}
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
  // 말풍선 배치. '위쪽 대상이면 아래, 아래쪽 대상이면 위' 규칙만으로는
  // 체험용 카드처럼 화면을 거의 다 채우는 대상에서 말풍선이 화면 밖으로
  // 밀려난다 — 투어 중에는 배경 스크롤을 잠그므로 내려볼 수도 없다.
  // 실제로 남는 공간을 재서 아래 → 위 → 좌측 → 화면 하단 고정 순으로 고른다.
  const TIP_H = 260;                 // 말풍선 대략 높이(제목+요약+항목 2개+버튼)
  const TIP_W = 340;                 // 좌측 배치일 때의 폭
  const EDGE = 16;                   // 화면 가장자리 여백
  const spaceBelow = window.innerHeight - (hole.top + hole.height);
  const spaceAbove = hole.top;
  const spaceLeft = hole.left;
  const centered: React.CSSProperties = {
    left: EDGE, right: EDGE, maxWidth: 420, margin: "0 auto",
  };
  const tipStyle: React.CSSProperties =
    spaceBelow >= TIP_H + GAP
      ? { ...centered, top: hole.top + hole.height + GAP }
    : spaceAbove >= TIP_H + GAP
      ? { ...centered, bottom: window.innerHeight - hole.top + GAP }
    : spaceLeft >= TIP_W + GAP + EDGE
      // 대상 왼쪽, 세로는 대상 중앙에 맞추되 화면 안으로 클램프
      ? { left: hole.left - GAP - TIP_W, width: TIP_W,
          top: Math.min(
            Math.max(EDGE, hole.top + hole.height / 2 - TIP_H / 2),
            window.innerHeight - TIP_H - EDGE) }
      // 사방에 자리가 없으면(모바일에서 큰 대상) 하단 고정 — 대상을 일부
      // 가리지만 안 보이는 것보다 낫다
      : { ...centered, bottom: EDGE };

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
        display: "flex", flexDirection: "column", gap: 12,
        textAlign: "center",
      }}>
        {body}
        {footer}
      </div>
    </div>
  );
}
