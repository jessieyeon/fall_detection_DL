import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

// MediaPipe Pose 33 관절 중 알아볼 만한 최소 연결선
const CONNECTIONS = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],   // 어깨·팔
  [11, 23], [12, 24], [23, 24],                        // 몸통
  [23, 25], [25, 27], [24, 26], [26, 28],              // 다리
];

export default function Live() {
  const canvasRef = useRef(null);
  const stateRef = useRef({ landmarks: null, tiles: [], rows: 2, cols: 2,
                            risk: 0, prog: [0, 3] });
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/live`);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      const s = stateRef.current;
      if (m.type === "pose") { s.landmarks = m.landmarks; s.risk = m.risk; s.prog = m.prog; }
      else if (m.type === "fall") { s.tiles = m.tiles; s.rows = m.rows; s.cols = m.cols; }
      else if (m.type === "reset") { s.tiles = []; }
    };

    let raf;
    const draw = () => {
      const cv = canvasRef.current;
      if (cv) {
        const ctx = cv.getContext("2d");
        const { width: W, height: H } = cv;
        ctx.clearRect(0, 0, W, H);
        const s = stateRef.current;

        // 타일 격자
        for (let r = 0; r < s.rows; r++)
          for (let c = 0; c < s.cols; c++) {
            const x = (c / s.cols) * W, y = (r / s.rows) * H;
            const idx = r * s.cols + c;
            ctx.fillStyle = s.tiles.includes(idx) ? "rgba(255,0,0,0.35)"
                                                  : "rgba(255,255,255,0.03)";
            ctx.fillRect(x, y, W / s.cols, H / s.rows);
            ctx.strokeStyle = "#3a3a3a";
            ctx.strokeRect(x, y, W / s.cols, H / s.rows);
          }

        // 스켈레톤
        if (s.landmarks) {
          ctx.strokeStyle = "#38bdf8";
          ctx.lineWidth = 2;
          for (const [a, b] of CONNECTIONS) {
            const pa = s.landmarks[a], pb = s.landmarks[b];
            if (pa && pb) {
              ctx.beginPath();
              ctx.moveTo(pa[0] * W, pa[1] * H);
              ctx.lineTo(pb[0] * W, pb[1] * H);
              ctx.stroke();
            }
          }
          ctx.fillStyle = "#fbbf24";
          for (const p of s.landmarks) {
            ctx.beginPath();
            ctx.arc(p[0] * W, p[1] * H, 3, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }
      raf = requestAnimationFrame(draw);
    };
    draw();

    return () => { cancelAnimationFrame(raf); ws.close(); };
  }, []);

  return (
    <div style={{ padding: 24 }}>
      <h1>실시간 중계</h1>
      <Link to="/mypage">← 마이페이지</Link>
      <p>상태: {connected ? "연결됨" : "연결 대기 중…"}</p>
      <canvas ref={canvasRef} width={480} height={480}
              style={{ background: "#111", borderRadius: 8, maxWidth: "100%" }} />
      <p style={{ color: "#888" }}>
        카메라 없이 시험하려면 서버에서 <code>python -m webservice.live_demo</code> 실행.
      </p>
    </div>
  );
}
