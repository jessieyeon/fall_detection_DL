import type { CSSProperties } from "react";
import { CANVAS_H, CANVAS_W } from "./skeleton";

/**
 * 실시간 화면(카메라·체험·데모)의 공통 레이아웃.
 *
 * 예전에는 영상 칸을 `minmax(0, 300px)` 로 잡았다. 넓은 모니터에서 세로로 긴
 * 영상이 300px 폭에 갇혀, 화면 아래 3분의 2가 빈 채로 남았다. 그렇다고 폭을
 * 100% 로 풀면 세로 2:3 영상이 화면을 넘겨서 스크롤해야 안내가 보인다.
 *
 * 그래서 **폭이 아니라 높이를 기준**으로 잡는다. 뷰포트 높이에 맞춰 영상을
 * 세우고 비율(2:3)로 폭을 역산하면, 스크롤 없이 화면을 가득 쓰면서 비율도
 * 지켜진다. 오른쪽 안내는 남는 폭을 차지한다.
 */

const ASPECT = `${CANVAS_W} / ${CANVAS_H}`;

/** 영상 + 안내를 나란히 놓는 그리드. 모바일은 위아래로 쌓는다. */
export function stageGrid(mobile: boolean): CSSProperties {
  return {
    display: "grid",
    gap: 16,
    alignItems: "start",
    // 첫 칸은 auto — 아래 mediaBox 가 정한 크기를 그대로 쓴다.
    gridTemplateColumns: mobile ? "1fr" : "auto minmax(260px, 1fr)",
  };
}

/** 영상(캔버스·video)을 감싸는 상자. 비율 고정, 높이는 화면에 맞춘다.
 *
 * 76vh 인 이유: 헤더·제목·여백을 빼고 남는 세로가 대략 이만큼이다. 100vh 로
 * 두면 페이지가 넘쳐 스크롤이 생긴다. 820px 상한은 초대형 모니터에서 영상만
 * 거대해지는 것을 막는다 — 그쯤 넘어가면 스켈레톤이 더 잘 보이지도 않는다. */
export function mediaBox(mobile: boolean): CSSProperties {
  return mobile
    ? { width: "100%", aspectRatio: ASPECT }
    : { height: "min(76vh, 820px)", aspectRatio: ASPECT };
}

/** 상자를 채우는 캔버스·video 공통 스타일. 비율이 다른 영상은 레터박스 처리. */
export const mediaFill: CSSProperties = {
  display: "block",
  width: "100%",
  height: "100%",
  objectFit: "contain",
};
