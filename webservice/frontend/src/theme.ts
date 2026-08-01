// 다온 디자인 토큰 — 네오브루탈리즘(굵은 검은 외곽선 + 고대비 + 각진 모서리).
import type { CSSProperties } from "react";

export const color = {
  bg: "#F8F9FF",
  ink: "#151C25",
  black: "#000000",
  white: "#FFFFFF",
  gray: "#4C4546",
  red: "#BA1A1A",
  blue1: "#D9E3F4",
  blue2: "#D6E0F1",
  blue3: "#E7EEFB",
} as const;

// 흰 배경 위에 안쪽으로 그린 검은 테두리(레이아웃을 밀지 않는 outline 사용).
export const edge = (w = 2, c: string = color.black): CSSProperties => ({
  outline: `${w}px solid ${c}`,
  outlineOffset: `-${w}px`,
});
