import { useEffect, useRef, useState } from "react";
import { color, font, radius } from "../theme";
import { Alert, Video, Wifi } from "../ui/icons";
import Card from "../ui/Card";
import Button from "../ui/Button";

/**
 * 내 카메라 체험 — 관람객 기기의 카메라로 낙상 감지를 직접 체험한다.
 *
 * 포즈 추출(MediaPipe Tasks)은 전부 이 브라우저 안에서 돈다. 서버로는 관절
 * 좌표 33개만 보내고 영상 픽셀은 절대 나가지 않는다 — '자세만 보고 영상은
 * 보내지 않는다'는 제품 약속이 코드 구조로 강제된다.
 *
 * 판정(모델·persistence·타일 선택)은 서버가 부스 파이프라인과 동일한 코드로
 * 수행한다. 브라우저마다 모델을 다시 구현하면 부스와 온라인의 판정이 어긋난다.
 */

const CDN = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/" +
  "pose_landmarker_lite/float16/1/pose_landmarker_lite.task";

const SEND_FPS = 20;                 // 서버 전송 상한. 판정 품질에 충분한 수준.
const CONNECTIONS: [number, number][] = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24],
  [23, 25], [25, 27], [24, 26], [26, 28],
];

type Phase = "loading" | "running" | "busy" | "unavailable" | "error";

type FallState = { tiles: number[]; rows: number; cols: number } | null;

export default function SelfCam({ onExit }: { onExit: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [risk, setRisk] = useState(0);
  const [prog, setProg] = useState<[number, number]>([0, 3]);
  const [fall, setFall] = useState<FallState>(null);

  // 최신 상태를 rAF 루프에서 읽기 위한 ref (state 클로저 고착 방지)
  const riskRef = useRef(0);
  const fallRef = useRef<FallState>(null);
  riskRef.current = risk;
  fallRef.current = fall;

  useEffect(() => {
    let stream: MediaStream | null = null;
    let ws: WebSocket | null = null;
    let landmarker: any = null;
    let raf = 0;
    let stopped = false;
    let lastSent = 0;
    let lastVideoTime = -1;

    const fail = (msg: string) => {
      if (stopped) return;
      setErrorMsg(msg);
      setPhase("error");
    };

    (async () => {
      // 1) 카메라. 요청이 가장 먼저다 — 권한 팝업이 늦게 뜨면 사용자는
      //    로딩이 멈춘 줄 안다.
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 640 } },
          audio: false,
        });
      } catch {
        fail("카메라 권한이 필요합니다. 브라우저 주소창의 카메라 아이콘에서 허용해 주세요.");
        return;
      }
      if (stopped) { stream.getTracks().forEach((t) => t.stop()); return; }
      const video = videoRef.current!;
      video.srcObject = stream;
      await video.play().catch(() => {});

      // 2) 포즈 모델 (CDN, 최초 1회 ~6MB — 이후 브라우저 캐시)
      try {
        const vision = await import(/* @vite-ignore */ `${CDN}/+esm`);
        const fileset = await vision.FilesetResolver.forVisionTasks(`${CDN}/wasm`);
        const make = (delegate: "GPU" | "CPU") =>
          vision.PoseLandmarker.createFromOptions(fileset, {
            baseOptions: { modelAssetPath: MODEL_URL, delegate },
            runningMode: "VIDEO",
            numPoses: 1,
          });
        landmarker = await make("GPU").catch(() => make("CPU"));
      } catch {
        fail("포즈 인식 모듈을 불러오지 못했습니다. 인터넷 연결을 확인해 주세요.");
        return;
      }
      if (stopped) return;

      // 3) 판정 서버 연결
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/ws/live/self`);
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.type === "ready") { setPhase("running"); setProg([0, m.persistence]); }
        else if (m.type === "busy") setPhase("busy");
        else if (m.type === "unavailable") setPhase("unavailable");
        else if (m.type === "self") { setRisk(m.risk); setProg(m.prog); }
        else if (m.type === "fall") setFall({ tiles: m.tiles, rows: m.rows, cols: m.cols });
        else if (m.type === "reset") setFall(null);
      };
      ws.onerror = () => fail("판정 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");

      // 4) 감지 + 그리기 루프
      const round = (v: number) => Math.round(v * 10000) / 10000;
      const loop = () => {
        if (stopped) return;
        raf = requestAnimationFrame(loop);
        const cv = canvasRef.current;
        if (!cv || video.readyState < 2) return;

        const W = (cv.width = video.videoWidth);
        const H = (cv.height = video.videoHeight);
        const ctx = cv.getContext("2d")!;

        // 거울 모드: 관람객은 거울처럼 보이는 화면을 기대한다.
        ctx.save();
        ctx.scale(-1, 1);
        ctx.drawImage(video, -W, 0, W, H);
        ctx.restore();
        ctx.fillStyle = "rgba(14,17,22,0.35)";
        ctx.fillRect(0, 0, W, H);

        const now = performance.now();
        let lm: number[][] | null = null;
        let wlm: number[][] | null = null;
        if (video.currentTime !== lastVideoTime) {
          lastVideoTime = video.currentTime;
          const res = landmarker.detectForVideo(video, now);
          if (res.landmarks?.[0]) {
            lm = res.landmarks[0].map((p: any) => [round(p.x), round(p.y), round(p.z)]);
            wlm = res.worldLandmarks?.[0]?.map(
              (p: any) => [round(p.x), round(p.y), round(p.z)]) ?? null;
          }
          // 전송 스로틀 — 판정에는 20fps 면 충분하고 서버 부하는 절반이 된다.
          if (ws?.readyState === WebSocket.OPEN && now - lastSent >= 1000 / SEND_FPS) {
            lastSent = now;
            ws.send(JSON.stringify({
              t: now / 1000, w: W, h: H, lm, wlm,
            }));
          }
        }

        if (lm) {
          const px = (p: number[]) => [(1 - p[0]) * W, p[1] * H] as const; // 거울 좌표
          ctx.lineCap = "round";
          ctx.shadowColor = "rgba(90,140,255,0.85)";
          ctx.shadowBlur = 12;
          ctx.strokeStyle = riskRef.current >= 0.5 ? "#FF6B6B" : "#6E9BFF";
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
        }

        // 바닥 타일(하드웨어 대응 시각화): 발동 시 해당 칸 점등
        const f = fallRef.current;
        const rows = f?.rows ?? 2, cols = f?.cols ?? 2;
        const floorY = H * 0.72, floorH = H - floorY;
        for (let r = 0; r < rows; r++)
          for (let c = 0; c < cols; c++) {
            const idx = r * cols + c;
            const cw = W / cols, ch = floorH / rows;
            const x = c * cw, y = floorY + r * ch;
            const fired = f?.tiles.includes(idx) ?? false;
            ctx.fillStyle = fired ? "rgba(225,60,60,0.45)" : "rgba(255,255,255,0.04)";
            ctx.fillRect(x + 3, y + 3, cw - 6, ch - 6);
            ctx.lineWidth = fired ? 2.5 : 1;
            ctx.strokeStyle = fired ? "#ff6b6b" : "rgba(120,150,210,0.3)";
            ctx.strokeRect(x + 3, y + 3, cw - 6, ch - 6);
          }
      };
      loop();
    })();

    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      ws?.close();
      landmarker?.close?.();
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  if (phase === "busy" || phase === "unavailable") {
    return (
      <Card raised style={{ padding: 24, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Alert size={18} color={color.amber} />
          <b style={{ fontSize: font.h2 }}>
            {phase === "busy" ? "지금은 체험 인원이 가득 찼습니다" : "지금은 체험을 준비 중입니다"}
          </b>
        </div>
        <p style={{ margin: 0, fontSize: font.small, color: color.inkSoft, lineHeight: 1.6 }}>
          {phase === "busy"
            ? "동시에 체험할 수 있는 인원이 정해져 있습니다. 잠시 후 다시 시도해 주세요."
            : "잠시 후 다시 시도해 주세요."}
        </p>
        <Button variant="ghost" onClick={onExit}>돌아가기</Button>
      </Card>
    );
  }

  if (phase === "error") {
    return (
      <Card raised style={{ padding: 24, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Alert size={18} color={color.red} />
          <b style={{ fontSize: font.h2 }}>체험을 시작하지 못했습니다</b>
        </div>
        <p style={{ margin: 0, fontSize: font.small, color: color.inkSoft, lineHeight: 1.6 }}>
          {errorMsg}
        </p>
        <Button variant="ghost" onClick={onExit}>돌아가기</Button>
      </Card>
    );
  }

  return (
    <>
      <Card pad={0} style={{ overflow: "hidden" }}>
        <div style={{ position: "relative", background: "#0E1116", lineHeight: 0 }}>
          <video ref={videoRef} playsInline muted style={{ display: "none" }} />
          <canvas ref={canvasRef}
                  style={{ display: "block", width: "100%", height: "auto",
                           aspectRatio: "4 / 3" }} />
          {phase === "loading" && (
            <div style={{
              position: "absolute", inset: 0, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 10, lineHeight: 1.5,
            }}>
              <Video size={28} color="rgba(255,255,255,0.6)" />
              <div style={{ fontSize: font.small, color: "rgba(255,255,255,0.8)" }}>
                카메라와 자세 인식을 준비하는 중…
              </div>
              <div style={{ fontSize: font.caption, color: "rgba(255,255,255,0.45)" }}>
                처음 한 번은 10초쯤 걸릴 수 있어요
              </div>
            </div>
          )}
          {phase === "running" && (
            <>
              <div style={{ position: "absolute", left: 12, top: 12, display: "flex", gap: 6 }}>
                <span style={{
                  padding: "3px 9px", fontSize: font.caption, fontWeight: 700,
                  borderRadius: radius.sm, background: color.red, color: color.white,
                }}>
                  내 카메라
                </span>
              </div>
              {/* 위험도 게이지 */}
              <div style={{
                position: "absolute", left: 12, right: 12, bottom: 12,
                padding: "8px 12px", borderRadius: radius.md,
                background: "rgba(0,0,0,0.55)", backdropFilter: "blur(4px)",
                display: "flex", alignItems: "center", gap: 10,
              }}>
                <span style={{ fontSize: font.caption, color: "rgba(255,255,255,0.8)", flexShrink: 0 }}>
                  낙상 위험
                </span>
                <div style={{ flex: 1, height: 8, borderRadius: 999, background: "rgba(255,255,255,0.15)" }}>
                  <div style={{
                    width: `${Math.min(100, risk * 100)}%`, height: "100%",
                    borderRadius: 999, transition: "width .15s",
                    background: risk >= 0.5 ? "#FF6B6B" : risk >= 0.1 ? "#FFB84D" : "#6E9BFF",
                  }} />
                </div>
                <span style={{
                  fontSize: font.caption, fontWeight: 700, flexShrink: 0,
                  color: prog[0] > 0 ? "#FFB84D" : "rgba(255,255,255,0.6)",
                }}>
                  {prog[0]}/{prog[1]}
                </span>
              </div>
              {fall && (
                <div style={{
                  position: "absolute", left: "50%", top: "38%",
                  transform: "translate(-50%,-50%)",
                  padding: "10px 20px", borderRadius: radius.md,
                  background: "rgba(225,60,60,0.92)", color: color.white,
                  fontSize: font.h2, fontWeight: 800, whiteSpace: "nowrap",
                }}>
                  낙상 감지! 완충 타일 작동
                </div>
              )}
            </>
          )}
        </div>
      </Card>

      <Card bg={color.brandTint} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
        <Wifi size={16} color={color.brand} />
        <span style={{ fontSize: font.small, color: color.ink, lineHeight: 1.6 }}>
          카메라 영상은 <b>이 기기 밖으로 나가지 않습니다.</b> AI가 인식한 자세
          좌표만 서버로 보내 낙상을 판정합니다. 화면 앞에서 천천히 주저앉거나
          몸을 기울여 보세요 — 진짜로 넘어질 필요는 없어요!
        </span>
      </Card>

      <Button variant="ghost" onClick={onExit}>체험 끝내기</Button>
    </>
  );
}
