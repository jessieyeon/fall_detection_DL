import { useEffect, useRef, useState } from "react";
import { color, font, radius } from "../theme";
import { Alert, Person, Video } from "../ui/icons";
import Card from "../ui/Card";
import Button from "../ui/Button";
import { useIsMobile } from "../useMedia";
import { CANVAS_H, CANVAS_W, drawScene } from "../ui/skeleton";
import { mediaBox, mediaFill, stageGrid } from "../ui/stage";

/**
 * 내 카메라 체험 — 관람객 기기의 카메라로 낙상 감지를 직접 체험한다.
 *
 * 포즈 추출(MediaPipe Tasks)은 전부 이 브라우저 안에서 돈다. 서버로는 관절
 * 좌표 33개(프레임당 ~1KB)만 보낸다 — 영상 픽셀을 올리면 대역폭도 서버 부하도
 * 감당이 안 되고, 판정에 필요한 정보는 좌표가 전부다.
 *
 * 판정(모델·persistence·타일 선택)은 서버가 부스 파이프라인과 동일한 코드로
 * 수행한다. 브라우저마다 모델을 다시 구현하면 부스와 온라인의 판정이 어긋난다.
 */

const CDN = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/" +
  "pose_landmarker_lite/float16/1/pose_landmarker_lite.task";

const SEND_FPS = 20;                 // 서버 전송 상한. 판정 품질에 충분한 수준.

/**
 * 이 화면에는 완충 타일 하드웨어(아두이노)가 붙어 있지 않다. 관람객 브라우저에서
 * 도는 체험이라 물리 장치가 있을 수 없다 — 부스의 실시간 감지와 다른 점이다.
 *
 * 그래서 판정이 '낙상'으로 떨어져도 타일을 켜거나 "작동" 이라고 말하지 않는다.
 * 실제로는 아무것도 펴지지 않는데 화면만 작동한 것처럼 보이면, 관람객이 제품
 * 성능을 잘못 이해한 채 돌아간다. 대신 왜 안 켜지는지를 화면 위에 밝힌다.
 * (이 화면에만 해당하므로 상수로 박아둔다. 실시간 감지는 영향받지 않는다.)
 */
const TILE_HARDWARE_CONNECTED = false;
const NO_TILE_NOTICE = "타일에 연결이 되어 있지 않아 타일 작동이 불가합니다";

type Phase = "loading" | "running" | "busy" | "unavailable" | "error";

export default function SelfCam({ onExit }: { onExit: () => void }) {
  const mobile = useIsMobile();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [errorMsg, setErrorMsg] = useState("");

  /** 마지막으로 검출된 관절 좌표.
   *
   * 화면 갱신(rAF, 60fps)이 카메라 프레임(보통 30fps)보다 빠르다. 새 프레임이
   * 아직 안 온 회차에 스켈레톤을 안 그리면 한 프레임씩 걸러 사람이 사라져
   * **심하게 깜빡인다.** 마지막 자세를 들고 있다가 다시 그려서 이어 붙인다. */
  const poseRef = useRef<number[][] | null>(null);

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
        // 판정 결과(self/fall)는 받되 화면에 쓰지 않는다 — 타일 하드웨어가
        // 없는 화면이라 점등·감지 표시를 하지 않기로 했다(위 상수 참고).
        if (m.type === "ready") setPhase("running");
        else if (m.type === "busy") setPhase("busy");
        else if (m.type === "unavailable") setPhase("unavailable");
      };
      ws.onerror = () => fail("판정 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");

      // 4) 감지 + 그리기 루프
      const round = (v: number) => Math.round(v * 10000) / 10000;
      const loop = () => {
        if (stopped) return;
        raf = requestAnimationFrame(loop);
        const cv = canvasRef.current;
        if (!cv || video.readyState < 2) return;

        const now = performance.now();
        if (video.currentTime !== lastVideoTime) {
          lastVideoTime = video.currentTime;
          const res = landmarker.detectForVideo(video, now);
          // 사람을 놓친 프레임에는 null 로 지운다. 마지막 자세를 계속 들고
          // 있으면 화면 밖으로 나간 뒤에도 유령처럼 남는다.
          const lm: number[][] | null = res.landmarks?.[0]
            ? res.landmarks[0].map((p: any) => [round(p.x), round(p.y), round(p.z)])
            : null;
          poseRef.current = lm;

          // 전송 스로틀 — 판정에는 20fps 면 충분하고 서버 부하는 절반이 된다.
          if (ws?.readyState === WebSocket.OPEN && now - lastSent >= 1000 / SEND_FPS) {
            lastSent = now;
            const wlm = res.worldLandmarks?.[0]?.map(
              (p: any) => [round(p.x), round(p.y), round(p.z)]) ?? null;
            // 판정에는 캔버스가 아니라 실제 영상 크기를 보낸다. 화면 비율을
            // 바꿨다고 판정 기준이 흔들리면 안 된다.
            ws.send(JSON.stringify({
              t: now / 1000, w: video.videoWidth, h: video.videoHeight, lm, wlm,
            }));
          }
        }

        // 실시간 감지 화면과 완전히 같은 렌더러로 그린다(ui/skeleton.ts).
        // 앞면 카메라라 좌우만 뒤집는다 — 거울이 아니면 손을 들었을 때
        // 반대쪽 팔이 올라가 보인다.
        cv.width = CANVAS_W;
        cv.height = CANVAS_H;
        drawScene(cv.getContext("2d")!, CANVAS_W, CANVAS_H, {
          landmarks: poseRef.current,
          // 하드웨어가 없으므로 격자는 그리되 점등은 하지 않는다(항상 빈 배열).
          tiles: [],
          rows: 2, cols: 2,
          mirror: true,
          placeholder: "사람이 감지되면 여기에 표시됩니다",
        });
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
    // 실시간 감지 화면과 같은 배치·크기(ui/stage.ts). 두 화면이 다른 크기로
    // 보이면 같은 기능이 다른 제품처럼 읽힌다.
    <div style={stageGrid(mobile)}>
      <Card pad={0} style={{ overflow: "hidden", ...mediaBox(mobile) }}>
        <div style={{
          position: "relative", background: "#0E1116", lineHeight: 0, height: "100%",
        }}>
          <video ref={videoRef} playsInline muted style={{ display: "none" }} />
          <canvas ref={canvasRef} width={CANVAS_W} height={CANVAS_H}
                  style={mediaFill} />
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
                {/* 부모가 lineHeight:0 이라(캔버스 아래 여백을 없애려고) 그대로 두면
                    글자 높이가 0으로 접혀 배지 밖으로 삐져나온다. 여기서 되돌린다. */}
                <span style={{
                  display: "inline-flex", alignItems: "center",
                  padding: "5px 10px", lineHeight: 1.3,
                  fontSize: font.caption, fontWeight: 700, whiteSpace: "nowrap",
                  borderRadius: radius.sm, background: color.red, color: color.white,
                }}>
                  내 카메라
                </span>
              </div>
              {!TILE_HARDWARE_CONNECTED && (
                <div style={{
                  position: "absolute", left: 12, right: 12, bottom: 12,
                  padding: "8px 12px", borderRadius: radius.md, lineHeight: 1.4,
                  background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)",
                  display: "flex", alignItems: "center", gap: 8,
                }}>
                  <Alert size={14} color={color.amber} />
                  <span style={{ fontSize: font.caption, color: "rgba(255,255,255,0.9)" }}>
                    {NO_TILE_NOTICE}
                  </span>
                </div>
              )}
            </>
          )}
        </div>
      </Card>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {/* 실시간 감지 화면과 같은 문구. 같은 안내를 두 화면이 다르게 말하면
            어느 쪽이 맞는지 관람객이 알 수 없다. */}
        <Card bg={color.brandTint} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
          <Person size={16} color={color.brand} />
          <span style={{ fontSize: font.small, color: color.ink, lineHeight: 1.6 }}>
            <b>발끝부터 머리까지</b> 카메라 화면 안에 모두 들어와야 자세를
            정확히 인식합니다.
            <br />
            몸의 일부가 잘리면 감지가 어려우니, 카메라 위치를 고정한 뒤
            다시 시작해 주세요.
          </span>
        </Card>

        {/* 체험을 멈추면 실시간 탭의 첫 화면(카메라 연결 버튼이 있는 곳)으로
            돌아간다. ghost 였을 때는 있는 줄도 모르고 탭을 옮겨 나가는 사람이
            많아 카메라가 계속 켜져 있었다 — 눈에 띄는 버튼으로 둔다. */}
        <Button variant="outline" onClick={onExit} style={{ alignSelf: "flex-start" }}>
          체험 멈추기
        </Button>
      </div>
    </div>
  );
}
