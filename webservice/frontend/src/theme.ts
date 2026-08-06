// 다온 디자인 토큰 — 보호자용 대시보드.
//
// 이전 버전은 시니어 본인이 쓰는 앱을 전제로 네오브루탈리즘(굵은 검은 외곽선 +
// 고대비 + 큰 글씨)을 썼다. 사용자가 보호자로 바뀌면서 그림자와 연한 보더 기반의
// 차분한 카드 스타일로 다시 잡았고, 글자도 전반적으로 줄였다.
import type { CSSProperties } from "react";

// ── 브랜드 컬러 ────────────────────────────────────────────────────────────
//
// ⚠️ 확인 필요: 삼성생명 전용 CI 의 정확한 HEX 는 공개 문서에서 찾지 못했다.
//    삼성 브랜드 아이덴티티 페이지(samsung.com/sec/about-us/brand-identity/
//    color-and-typo)는 "삼성 블루"를 이미지로만 제시하고 값은 명시하지 않는다.
//    아래 값은 널리 통용되는 삼성 코퍼레이트 블루다. 삼성생명 브랜드 가이드에서
//    정확한 값을 확인하면 이 두 줄만 고치면 전체에 반영된다.
const BRAND = "#1428A0";
const BRAND_DARK = "#0E1C70";

export const color = {
  brand: BRAND,
  brandDark: BRAND_DARK,
  brandTint: "#EEF2FC",     // 아주 연한 배경
  brandTint2: "#DCE4F7",    // 강조 배경

  bg: "#F5F7FA",
  surface: "#FFFFFF",
  ink: "#131722",           // 본문
  inkSoft: "#4A5568",       // 보조 텍스트
  inkFaint: "#8A93A3",      // 라벨·캡션
  line: "#E3E7EE",          // 보더
  lineStrong: "#CDD4E0",

  red: "#C62828",
  redTint: "#FDECEC",
  amber: "#B45309",
  amberTint: "#FEF3E2",
  green: "#2E7D32",
  greenTint: "#E9F5EA",

  white: "#FFFFFF",
  black: "#000000",

  // 하위 호환 — 예전 이름을 쓰는 곳이 남아 있어도 깨지지 않게 한다
  gray: "#4A5568",
  blue1: "#DCE4F7",
  blue2: "#EEF2FC",
  blue3: "#F5F7FA",
} as const;

// ── 타이포 ─────────────────────────────────────────────────────────────────
// 시니어용에서 쓰던 크기(본문 18, 제목 24)를 보호자용으로 낮췄다.
export const font = {
  h1: 20,
  h2: 16,
  body: 14,
  small: 13,
  caption: 12,
} as const;

export const radius = { sm: 6, md: 10, lg: 14 } as const;

export const shadow = {
  card: "0 1px 2px rgba(19,23,34,0.04), 0 1px 3px rgba(19,23,34,0.06)",
  raised: "0 4px 12px rgba(19,23,34,0.08)",
  brand: "0 2px 8px rgba(20,40,160,0.20)",
} as const;

/**
 * 예전 네오브루탈리즘 헬퍼. 굵은 검은 outline 을 그리던 것을 연한 보더로 바꿨다.
 *
 * 호출부가 열 군데 넘게 흩어져 있어 한 번에 지우면 전부 손봐야 한다. 시그니처를
 * 유지한 채 안쪽만 새 스타일로 바꿔서, 남아 있는 호출부도 자동으로 새 디자인을
 * 따르게 했다. 새로 쓰는 코드에서는 쓰지 말 것.
 *
 * @deprecated Card / Button 컴포넌트나 `border` 를 직접 쓰세요.
 */
export const edge = (_w = 1, c: string = color.line): CSSProperties => ({
  border: `1px solid ${c}`,
  borderRadius: radius.md,
});

/** 화면 폭이 좁은지 판단하는 경계. 데스크톱/모바일 분기 기준. */
export const MOBILE_MAX = 768;
