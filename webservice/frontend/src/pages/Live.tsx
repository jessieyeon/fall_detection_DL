import { useEffect, useRef, useState } from "react";
import { color, edge } from "../theme";
import { Wifi, Phone } from "../ui/icons";
import AppShell from "../ui/AppShell";
import Card from "../ui/Card";
import Button from "../ui/Button";

const CONNECTIONS: [number, number][] = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24],
  [23, 25], [25, 27], [24, 26], [26, 28],
];
const LOCATIONS = ["거실", "침실", "주방", "화장실"];
const FLOOR_TOP = 0.6;   // 타일 바닥 띠 시작 위치(위에서 60% 지점 아래 = 발 밑)
type LiveState = { landmarks: number[][] | null; tiles: number[]; rows: number; cols: number };

export default function Live() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<LiveState>({ landmarks: null, tiles: [], rows: 2, cols: 2 });
  const lastPose = useRef<number | null>(null);
  const [location, setLocation] = useState("거실");
  const [alerting, setAlerting] = useState(false);
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 2000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let ws: WebSocket | undefined;
    let retryTimer: ReturnType<typeof setTimeout>;
    let mounted = true;
    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/ws/live`);
      ws.onclose = () => { if (mounted) retryTimer = setTimeout(connect, 1500); };
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        const s = stateRef.current;
        if (m.type === "pose") { s.landmarks = m.landmarks; lastPose.current = Date.now(); }
        else if (m.type === "fall") { s.tiles = m.tiles || []; s.rows = m.rows || s.rows; s.cols = m.cols || s.cols; }
        else if (m.type === "reset") { s.tiles = []; }
      };
    };
    connect();

    let raf = 0;
    const draw = () => {
      const cv = canvasRef.current;
      if (cv) {
        const ctx = cv.getContext("2d")!;
        const { width: W, height: H } = cv;
        ctx.clearRect(0, 0, W, H);
        const s = stateRef.current;
        // 바닥 타일 격자 — 화면 아래쪽 바닥 띠(발 밑)에만 그린다. 발사된 타일은 빨강.
        const floorY = H * FLOOR_TOP, floorH = H - floorY;
        for (let r = 0; r < s.rows; r++)
          for (let c = 0; c < s.cols; c++) {
            const idx = r * s.cols + c;
            const cwid = W / s.cols, chei = floorH / s.rows;
            const x = c * cwid, y = floorY + r * chei;
            const fired = s.tiles.includes(idx);
            ctx.fillStyle = fired ? "rgba(186,26,26,0.55)" : "rgba(255,255,255,0.07)";
            ctx.fillRect(x, y, cwid, chei);
            ctx.lineWidth = fired ? 4 : 2;
            ctx.strokeStyle = fired ? "#ff6b6b" : "rgba(255,255,255,0.55)";
            ctx.strokeRect(x + ctx.lineWidth / 2, y + ctx.lineWidth / 2, cwid - ctx.lineWidth, chei - ctx.lineWidth);
            ctx.fillStyle = "rgba(255,255,255,0.7)";
            ctx.font = "bold 20px sans-serif";
            ctx.fillText(String(idx), x + 10, y + 28);
          }
        if (s.landmarks) {
          ctx.strokeStyle = "#38bdf8"; ctx.lineWidth = 2;
          for (const [a, b] of CONNECTIONS) {
            const pa = s.landmarks[a], pb = s.landmarks[b];
            if (pa && pb) { ctx.beginPath(); ctx.moveTo(pa[0] * W, pa[1] * H); ctx.lineTo(pb[0] * W, pb[1] * H); ctx.stroke(); }
          }
          ctx.fillStyle = "#fbbf24";
          for (const p of s.landmarks) { ctx.beginPath(); ctx.arc(p[0] * W, p[1] * H, 4, 0, Math.PI * 2); ctx.fill(); }
        }
      }
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => { mounted = false; clearTimeout(retryTimer); cancelAnimationFrame(raf); ws?.close(); };
  }, []);

  // 최근에 포즈 데이터를 받고 있으면 ON(연결됨), 아니면 OFF.
  const on = lastPose.current != null && Date.now() - lastPose.current < 5000;
  const activity = lastPose.current == null ? "감지 대기 중"
    : (() => { const s = Math.floor((Date.now() - lastPose.current) / 1000); return s < 60 ? `${s}초 전` : `${Math.floor(s / 60)}분 전`; })();

  function callEmergency() {
    setAlerting(true);
    setTimeout(() => setAlerting(false), 6000);
  }

  return (
    <AppShell active="monitor">
      {/* 위치 입력 */}
      <div>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>위치 입력</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {LOCATIONS.map((r) => (
            <button key={r} onClick={() => setLocation(r)}
              style={{ padding: "8px 14px", fontSize: 16, fontWeight: 700, ...edge(2),
                       background: location === r ? color.black : color.white, color: location === r ? color.white : color.ink }}>
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* 실시간 피드(타일 + 사람 스켈레톤). 세로로 긴 9:16 비율 */}
      <div style={{ position: "relative", background: color.black, ...edge(2) }}>
        <canvas ref={canvasRef} width={480} height={854} style={{ display: "block", width: "100%", height: "auto" }} />
        <div style={{ position: "absolute", left: 12, top: 12, display: "flex", gap: 8 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6, background: on ? color.red : color.gray, color: color.white, padding: "4px 10px", fontSize: 14, fontWeight: 700, ...edge(2, color.white) }}>
            <span style={{ width: 8, height: 8, borderRadius: 8, background: color.white }} /> {on ? "ON" : "OFF"}
          </span>
          <span style={{ background: "rgba(0,0,0,0.5)", color: color.white, padding: "4px 10px", fontSize: 14, fontWeight: 700, ...edge(2, color.white) }}>{location}</span>
        </div>
      </div>

      {/* 상태 */}
      <Card style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: 16 }}>
        <div>
          <div style={{ color: color.gray, fontSize: 15 }}>마지막 활동 감지</div>
          <div style={{ fontWeight: 700 }}>{activity}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: on ? color.ink : color.gray }}>
          <Wifi size={20} />
          <span style={{ fontWeight: 700 }}>{on ? "신호 양호" : "연결 대기"}</span>
        </div>
      </Card>

      {/* 긴급 전화 — 실제 발신 대신 알림 표시(MVP) */}
      <Button variant="danger" big full icon={<Phone color="white" />} onClick={callEmergency}
              style={{ flexDirection: "column", gap: 4 }}>
        긴급 전화
        <span style={{ fontSize: 14, fontWeight: 700 }}>119 / 지역 응급 서비스</span>
      </Button>
      {alerting && (
        <Card bg={color.red} style={{ color: color.white, textAlign: "center", fontWeight: 700, fontSize: 18 }}>
          🚨 긴급 전화 알림을 보냈습니다. 곧 응급 서비스로 연결됩니다.
        </Card>
      )}
    </AppShell>
  );
}
