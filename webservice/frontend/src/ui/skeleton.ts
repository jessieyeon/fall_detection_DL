/**
 * 스켈레톤·바닥 타일 렌더링 — 실시간 감지(Live)와 내 카메라 체험(SelfCam)이 공유한다.
 *
 * 두 화면이 각자 그리던 시절에는 같은 기능이 다른 제품처럼 보였다. 실시간은
 * 뼈대에 관절점과 머리 원까지 그리는데 체험은 선만 그렸고, 타일을 그리는 순서도
 * 반대라 체험 쪽은 타일이 사람을 덮었다. 렌더링을 한 군데로 모아 그 차이를 없앤다.
 */

export const CONNECTIONS: [number, number][] = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24],
  [23, 25], [25, 27], [24, 26], [26, 28],
];

/** 관절점을 찍을 랜드마크. 손가락·발가락까지 찍으면 지저분하다. */
const JOINTS = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28];

/** 캔버스 세로에서 바닥(타일 격자)이 시작되는 지점. */
export const FLOOR_TOP = 0.6;

/** 실시간·체험이 공유하는 캔버스 크기(세로로 긴 직사각형). */
export const CANVAS_W = 480;
export const CANVAS_H = 720;

export type Scene = {
  landmarks: number[][] | null;
  /** 점등할 타일 번호. 아두이노가 없으면 항상 빈 배열이다. */
  tiles: number[];
  rows: number;
  cols: number;
  /** 앞면 카메라(체험)는 좌우를 뒤집어야 거울처럼 자연스럽다. */
  mirror?: boolean;
  /** 사람이 없을 때 안내 문구를 캔버스에 그릴지. */
  placeholder?: string;
};

function drawBackground(ctx: CanvasRenderingContext2D, W: number, H: number) {
  const bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, "#101623");
  bg.addColorStop(1, "#1A2438");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);
}

function drawFloor(ctx: CanvasRenderingContext2D, W: number, H: number,
                   tiles: number[], rows: number, cols: number) {
  const floorY = H * FLOOR_TOP, floorH = H - floorY;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const fired = tiles.includes(r * cols + c);
      const cw = W / cols, ch = floorH / rows;
      const x = c * cw, y = floorY + r * ch;
      ctx.fillStyle = fired ? "rgba(225,60,60,0.45)" : "rgba(255,255,255,0.03)";
      ctx.fillRect(x + 3, y + 3, cw - 6, ch - 6);
      ctx.lineWidth = fired ? 2.5 : 1;
      ctx.strokeStyle = fired ? "#ff6b6b" : "rgba(120,150,210,0.25)";
      ctx.strokeRect(x + 3, y + 3, cw - 6, ch - 6);
    }
  }
}

function drawPose(ctx: CanvasRenderingContext2D, W: number, H: number,
                  lm: number[][], mirror: boolean) {
  const px = (p: number[]) =>
    [(mirror ? 1 - p[0] : p[0]) * W, p[1] * H] as const;

  // 뼈대: 은은한 광 + 굵고 둥근 선. 브랜드 블루 톤.
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = "rgba(90,140,255,0.85)";
  ctx.shadowBlur = 14;
  ctx.strokeStyle = "#6E9BFF";
  ctx.lineWidth = 5;
  for (const [a, b] of CONNECTIONS) {
    if (lm[a] && lm[b]) {
      ctx.beginPath();
      ctx.moveTo(...px(lm[a]));
      ctx.lineTo(...px(lm[b]));
      ctx.stroke();
    }
  }
  ctx.shadowBlur = 0;

  // 관절: 흰 테두리를 두른 점.
  for (const i of JOINTS) {
    if (!lm[i]) continue;
    const [x, y] = px(lm[i]);
    ctx.beginPath(); ctx.arc(x, y, 6, 0, Math.PI * 2);
    ctx.fillStyle = "#FFFFFF"; ctx.fill();
    ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fillStyle = "#3D6DE8"; ctx.fill();
  }

  // 머리: 코를 중심으로, 반지름은 어깨너비에 비례.
  const nose = lm[0], ls = lm[11], rs = lm[12];
  if (nose && ls && rs) {
    const [nx, ny] = px(nose);
    const headR = Math.max(10, Math.hypot(
      (ls[0] - rs[0]) * W, (ls[1] - rs[1]) * H) * 0.32);
    ctx.beginPath(); ctx.arc(nx, ny, headR, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(110,155,255,0.25)"; ctx.fill();
    ctx.lineWidth = 3; ctx.strokeStyle = "#6E9BFF"; ctx.stroke();
  }
}

/** 배경 → 바닥 타일 → 사람 순서로 한 프레임을 그린다.
 *
 * 순서가 중요하다. 사람을 먼저 그리면 타일이 그 위를 덮어 스켈레톤이 반쯤
 * 가려진다(체험 화면에서 실제로 그랬다). */
export function drawScene(ctx: CanvasRenderingContext2D, W: number, H: number,
                          s: Scene) {
  drawBackground(ctx, W, H);
  drawFloor(ctx, W, H, s.tiles, s.rows, s.cols);
  if (s.landmarks) {
    drawPose(ctx, W, H, s.landmarks, s.mirror ?? false);
  } else if (s.placeholder) {
    ctx.fillStyle = "rgba(255,255,255,0.35)";
    ctx.font = "15px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(s.placeholder, W / 2, H / 2);
  }
}
