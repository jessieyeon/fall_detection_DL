import { useEffect, useRef, useState } from "react";
import { color, edge } from "../theme";
import { Wifi, Mic, Phone } from "../ui/icons";
import AppShell from "../ui/AppShell";
import Card from "../ui/Card";
import Button from "../ui/Button";

// MediaPipe Pose 33 관절 중 알아볼 만한 최소 연결선
const CONNECTIONS: [number, number][] = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24],
  [23, 25], [25, 27], [24, 26], [26, 28],
];

type LiveState = { landmarks: number[][] | null; tiles: number[]; rows: number; cols: number };

export default function Live() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<LiveState>({ landmarks: null, tiles: [], rows: 2, cols: 2 });
  const lastPose = useRef<number | null>(null);
  const [connected, setConnected] = useState(false);
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 5000); // 상대시간 갱신
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let ws: WebSocket | undefined;
    let retryTimer: ReturnType<typeof setTimeout>;
    let mounted = true;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws/live`);
      ws.onopen = () => { if (mounted) setConnected(true); };
      ws.onclose = () => {
        if (!mounted) return;
        setConnected(false);
        retryTimer = setTimeout(connect, 1500);
      };
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
        for (let r = 0; r < s.rows; r++)
          for (let c = 0; c < s.cols; c++) {
            const x = (c / s.cols) * W, y = (r / s.rows) * H;
            ctx.fillStyle = s.tiles.includes(r * s.cols + c) ? "rgba(186,26,26,0.4)" : "rgba(255,255,255,0.03)";
            ctx.fillRect(x, y, W / s.cols, H / s.rows);
            ctx.strokeStyle = "rgba(255,255,255,0.15)";
            ctx.strokeRect(x, y, W / s.cols, H / s.rows);
          }
        if (s.landmarks) {
          ctx.strokeStyle = "#38bdf8"; ctx.lineWidth = 2;
          for (const [a, b] of CONNECTIONS) {
            const pa = s.landmarks[a], pb = s.landmarks[b];
            if (pa && pb) { ctx.beginPath(); ctx.moveTo(pa[0] * W, pa[1] * H); ctx.lineTo(pb[0] * W, pb[1] * H); ctx.stroke(); }
          }
          ctx.fillStyle = "#fbbf24";
          for (const p of s.landmarks) { ctx.beginPath(); ctx.arc(p[0] * W, p[1] * H, 3, 0, Math.PI * 2); ctx.fill(); }
        }
      }
      raf = requestAnimationFrame(draw);
    };
    draw();

    return () => { mounted = false; clearTimeout(retryTimer); cancelAnimationFrame(raf); ws?.close(); };
  }, []);

  const activity = lastPose.current == null ? "감지 대기 중"
    : (() => { const s = Math.floor((Date.now() - lastPose.current) / 1000); return s < 60 ? `${s}초 전` : `${Math.floor(s / 60)}분 전`; })();

  return (
    <AppShell active="monitor" right={<Wifi size={20} color={connected ? color.ink : color.gray} />}>
      {/* 라이브 피드(스켈레톤 캔버스) */}
      <div style={{ position: "relative", background: color.black, ...edge(2) }}>
        <canvas ref={canvasRef} width={640} height={400} style={{ display: "block", width: "100%", height: "auto" }} />
        <div style={{ position: "absolute", left: 12, top: 12, display: "flex", gap: 8 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6, background: color.red, color: color.white, padding: "4px 10px", fontSize: 14, fontWeight: 700, ...edge(2, color.white) }}>
            <span style={{ width: 8, height: 8, borderRadius: 8, background: color.white }} /> LIVE
          </span>
          <span style={{ background: "rgba(0,0,0,0.5)", color: color.white, padding: "4px 10px", fontSize: 14, fontWeight: 700, ...edge(2, color.white) }}>Living Room</span>
        </div>
      </div>

      {/* 상태 */}
      <Card style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: 16 }}>
        <div>
          <div style={{ color: color.gray, fontSize: 15 }}>마지막 활동 감지</div>
          <div style={{ fontWeight: 700 }}>{activity}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: connected ? color.ink : color.gray }}>
          <Wifi size={20} />
          <span style={{ fontWeight: 700 }}>{connected ? "신호 양호" : "연결 대기"}</span>
        </div>
      </Card>

      {/* 액션 (Speak to Home 은 데모 장식, Call Emergency 는 전화 연결) */}
      <Button variant="outline" big full icon={<Mic />}>Speak to Home</Button>
      <Button as="a" href="tel:119" variant="danger" big full icon={<Phone color="white" />}
              style={{ flexDirection: "column", gap: 4, textDecoration: "none", padding: "16px 24px" }}>
        CALL EMERGENCY
        <span style={{ fontSize: 14, fontWeight: 700 }}>119 / 지역 응급 서비스로 연결</span>
      </Button>
      <p style={{ margin: 0, textAlign: "center", color: color.gray, fontSize: 15 }}>
        카메라 없이 시험하려면 서버에서 <code>python -m webservice.live_demo</code> 실행.
      </p>
    </AppShell>
  );
}
