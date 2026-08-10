import { useEffect, useRef, useState } from "react";
import { color, font, radius } from "../theme";
import { Video, Wifi, Alert, MapPin, Pause, Play, Person } from "../ui/icons";
import AppShell from "../ui/AppShell";
import Card from "../ui/Card";
import Button from "../ui/Button";
import SelfCam from "./SelfCam";
import { useIsMobile } from "../useMedia";
import { listCameras } from "../api";
import { drawScene } from "../ui/skeleton";
import { mediaBox, mediaFill, stageGrid } from "../ui/stage";

/**
 * 데모 영상 경로. 영상 파일은 별도 제공 예정이므로 경로만 상수로 둔다.
 * 파일을 webservice/frontend/public/ 에 넣으면 이 경로로 서빙된다.
 */
const DEMO_VIDEO_SRC = "/demo/fall-detection-demo.mp4";
const DEMO_POSTER_SRC = "/demo/fall-detection-demo.jpg";

/** 감지 파이프라인이 밀어넣는 카메라 영상(MJPEG). main.py --live-url 이 채운다.
 *  화면에는 스켈레톤만 그리므로 지금은 쓰지 않고, 진단용으로만 남겨둔다.
 *  카메라를 고를 때는 `?device=<기기키>` 를 붙인다. */
const STREAM_SRC = "/api/live/stream.mjpg";


/** 연결 진단 패널을 보여줄지. 개발 서버이거나 ?diag=1 을 붙였을 때만 켠다.
 *  부스 노트북에서 배포 빌드를 그대로 쓰면서 진단이 필요할 때가 있어 뒷문을 남긴다. */
const showDiag = import.meta.env.DEV ||
  new URLSearchParams(window.location.search).get("diag") === "1";

type LiveState = { landmarks: number[][] | null; tiles: number[]; rows: number; cols: number };
type Stage = "idle" | "searching" | "none" | "demo" | "self";

/** 감지 파이프라인이 붙어 있는지 확인 — WebSocket 으로 포즈가 들어오는지 본다.
 *
 * 페이지에 들어오는 즉시 연결한다. '카메라 연결'을 누른 뒤에 붙이면 WebSocket
 * 핸드셰이크와 첫 포즈 수신까지 기다려야 해서, 실제로 파이프라인이 돌고 있는데도
 * 타임아웃에 걸려 '카메라 없음'으로 빠진다. */
function useLiveFeed(canvasRef: React.RefObject<HTMLCanvasElement>,
                     pausedRef: React.RefObject<boolean>,
                     deviceRef: React.RefObject<string>) {
  const stateRef = useRef<LiveState>({ landmarks: null, tiles: [], rows: 2, cols: 2 });
  const lastPose = useRef<number | null>(null);

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
        // 여러 카메라가 같은 소켓으로 들어온다. 지금 보고 있는 것만 그린다.
        // device 가 없는 메시지는 익명 파이프라인(기존 실행 방식)이라 항상 받는다.
        const dev = deviceRef.current ?? "";
        if (m.device && dev && m.device !== dev) return;
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
      // 일시정지 중에는 캔버스를 건드리지 않는다 — 마지막 화면이 그대로 멈춰 있어야
      // 무엇 때문에 멈췄는지(자세, 타일) 들여다볼 수 있다.
      if (cv && !pausedRef.current) {
        const s = stateRef.current;
        drawScene(cv.getContext("2d")!, cv.width, cv.height, {
          landmarks: s.landmarks, tiles: s.tiles, rows: s.rows, cols: s.cols,
          placeholder: "사람이 감지되면 여기에 표시됩니다",
        });
      }
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => { mounted = false; clearTimeout(retryTimer); cancelAnimationFrame(raf); ws?.close(); };
  }, [canvasRef, pausedRef]);

  return lastPose;
}

type Diag = {
  reachable: boolean; frames: number; streaming: boolean; paused: boolean;
  /** 지금 영상이 들어오고 있는 카메라 목록 */
  devices: string[];
};

/** 카메라 연결을 끊거나 다시 잇는다. 실제로 장치를 놓는 것은 감지 파이프라인이고,
 *  여기서는 서버에 의사만 남긴다(파이프라인이 0.5초마다 가져간다). */
async function setCameraPaused(paused: boolean, device: string) {
  const r = await fetch("/api/live/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paused, device }),
  });
  if (!r.ok) throw new Error("카메라 제어에 실패했습니다");
  return (await r.json()).paused as boolean;
}

/** 서버가 파이프라인으로부터 프레임을 받고 있는지 주기적으로 확인한다.
 *
 * WebSocket 과 별개의 신호라, 'ws 는 막혔는데 파이프라인은 도는' 경우를 잡아낸다.
 * 실패 원인을 화면에 그대로 보여주기 위한 진단 용도이기도 하다. */
function useServerStatus(device: string): Diag {
  const [diag, setDiag] = useState<Diag>({
    reachable: true, frames: 0, streaming: false, paused: false, devices: [],
  });
  const prev = useRef<{ frames: number; at: number } | null>(null);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const q = device ? `?device=${encodeURIComponent(device)}` : "";
        const r = await fetch(`/api/live/status${q}`, { cache: "no-store" });
        if (!r.ok) throw new Error();
        const { frames, paused, stream_devices } = await r.json();
        if (!alive) return;
        const last = prev.current;
        // 프레임 수가 '늘고 있어야' 살아 있는 것이다. 값이 0이 아니어도
        // 멈춰 있으면 파이프라인이 종료된 뒤 남은 숫자일 뿐이다.
        const streaming = last != null && frames > last.frames;
        prev.current = { frames, at: Date.now() };
        setDiag({ reachable: true, frames, streaming, paused: !!paused,
                  devices: stream_devices ?? [] });
      } catch {
        if (alive) setDiag((d) => ({ ...d, reachable: false, streaming: false }));
      }
    };
    poll();
    const id = setInterval(poll, 1500);
    return () => { alive = false; clearInterval(id); };
  }, [device]);

  return diag;
}

export default function Live() {
  const mobile = useIsMobile();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [videoBroken, setVideoBroken] = useState(false);
  const [streamBroken, setStreamBroken] = useState(false);
  // 서버가 진실이지만 폴링이 1.5초라 눌렀을 때 즉시 반응하도록 잠깐 덮어쓴다.
  const [pendingPause, setPendingPause] = useState<boolean | null>(null);
  const [controlError, setControlError] = useState("");
  const [, setTick] = useState(0);
  // '내 카메라 체험' 가능 여부. 서버에 모델이 없으면 버튼 자체를 숨긴다.
  const [selfAvailable, setSelfAvailable] = useState(false);

  useEffect(() => {
    fetch("/api/live/self/available")
      .then((r) => r.json())
      .then((d) => setSelfAvailable(!!d.available))
      .catch(() => {});
  }, []);

  // 보고 있는 카메라. 빈 문자열이면 '익명 파이프라인'(기기키 없이 띄운 경우).
  const [device, setDevice] = useState("");
  // device_key 는 사람이 읽을 값이 아니다(daon-cam-302). 등록된 이름·설치 공간을
  // 가져와 화면에는 '3층 복도'처럼 보여준다.
  const [cameraNames, setCameraNames] = useState<Record<string, string>>({});
  const [cameraPlaces, setCameraPlaces] = useState<Record<string, string>>({});

  useEffect(() => {
    listCameras()
      .then((cs) => {
        setCameraNames(Object.fromEntries(cs.map((c) => [c.device_key, c.name])));
        setCameraPlaces(Object.fromEntries(cs.map((c) => [c.device_key, c.location])));
      })
      .catch(() => {});
  }, []);
  const diag = useServerStatus(device);
  const paused = pendingPause ?? diag.paused;

  // 카메라가 하나뿐이면 자동으로 그걸 보고 있게 한다 — 탭을 누르게 만들 이유가 없다.
  useEffect(() => {
    if (!device && diag.devices.length === 1) setDevice(diag.devices[0]);
  }, [device, diag.devices]);

  // 서버가 우리 요청을 반영하면 임시 덮어쓰기를 푼다.
  useEffect(() => {
    if (pendingPause !== null && diag.paused === pendingPause) setPendingPause(null);
  }, [diag.paused, pendingPause]);

  // 렌더 루프(requestAnimationFrame)가 최신 값을 읽어야 해서 ref 로 넘긴다.
  // state 를 바로 넘기면 effect 안의 클로저가 옛 값을 붙들고 있다.
  const pausedRef = useRef(false);
  pausedRef.current = paused;

  const deviceRef = useRef("");
  deviceRef.current = device;

  const lastPose = useLiveFeed(canvasRef, pausedRef, deviceRef);

  async function togglePause() {
    const next = !paused;
    setControlError("");
    setPendingPause(next);
    try {
      await setCameraPaused(next, device);
    } catch (err) {
      setPendingPause(null);
      setControlError((err as Error).message);
    }
  }

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 500);
    return () => clearInterval(id);
  }, []);

  // 카메라가 붙었는지는 두 신호 중 **하나만** 살아 있어도 인정한다.
  //   · WebSocket 으로 들어오는 포즈 (스켈레톤)
  //   · 서버가 받은 프레임 수의 증가 (영상)
  // WebSocket 만 보면, 프록시나 방화벽이 ws 를 막는 환경에서 실제로 파이프라인이
  // 돌고 있는데도 '카메라 없음'이 된다.
  const poseOn = lastPose.current != null && Date.now() - lastPose.current < 5000;
  // 일시 해제 중에는 프레임이 안 오는 게 정상이므로 '연결 없음'으로 떨어뜨리면 안 된다.
  // 다만 한 번도 붙은 적 없는데 플래그만 남아 있는 경우는 제외한다.
  const on = poseOn || diag.streaming || (paused && diag.frames > 0);

  // '카메라 연결' → 최대 3초간 포즈 수신을 기다린다. 들어오면 실시간 화면,
  // 안 들어오면 부스 안내. 이미 연결돼 있으면 즉시 넘어간다.
  function connect() {
    if (on) { setStage("demo"); return; }
    setStage("searching");
    const deadline = Date.now() + 3000;
    const tick = setInterval(() => {
      const live = lastPose.current != null && Date.now() - lastPose.current < 5000;
      if (live || Date.now() > deadline) {
        clearInterval(tick);
        setStage(live ? "demo" : "none");
      }
    }, 200);
  }

  return (
    <AppShell active="monitor">
      <h1 style={{ margin: 0, fontSize: font.h1, fontWeight: 700 }}>실시간 감지</h1>

      {stage === "idle" && (
        <Card raised style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          gap: 16, padding: "40px 24px", textAlign: "center",
        }}>
          <span style={{
            width: 56, height: 56, borderRadius: 16,
            background: on ? color.greenTint : color.brandTint,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <Video size={26} color={on ? color.green : color.brand} />
          </span>
          <div>
            <div style={{ fontSize: font.h2, fontWeight: 700 }}>
              {on ? "카메라가 감지되었습니다" : "카메라가 연결되지 않았습니다"}
            </div>
            <p style={{ margin: "6px 0 0", fontSize: font.small, color: color.inkSoft, lineHeight: 1.6 }}>
              {on
                ? "지금 바로 실시간 낙상 감지 화면을 볼 수 있습니다."
                : "집에 설치된 다온 카메라를 연결해 주세요."}
            </p>
          </div>
          <Button big onClick={connect} icon={<Video size={17} color={color.white} />}>
            {on ? "실시간 화면 보기" : "카메라 연결"}
          </Button>
          {selfAvailable && !on && (
            <Button variant="ghost" onClick={() => setStage("self")}>
              지금 이 기기 카메라로 체험하기
            </Button>
          )}
        </Card>
      )}

      {stage === "self" && <SelfCam onExit={() => setStage("idle")} />}

      {stage === "searching" && (
        <Card style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          gap: 14, padding: "44px 24px",
        }}>
          <Spinner />
          <div style={{ fontSize: font.body, color: color.inkSoft }}>카메라를 찾는 중…</div>
        </Card>
      )}

      {stage === "none" && (
        <>
          <Card raised style={{ padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
              <span style={{
                width: 34, height: 34, flexShrink: 0, borderRadius: 10,
                background: color.amberTint, display: "flex",
                alignItems: "center", justifyContent: "center",
              }}>
                <Alert size={17} color={color.amber} />
              </span>
              <div>
                <div style={{ fontSize: font.h2, fontWeight: 700 }}>
                  연결할 수 있는 카메라가 없습니다
                </div>
                <p style={{ margin: "6px 0 0", fontSize: font.small, color: color.inkSoft, lineHeight: 1.7 }}>
                  지금은 온라인 체험이라 집에 설치된 카메라가 연결되어 있지 않습니다.
                  <br />
                  {selfAvailable ? (
                    <b style={{ color: color.ink }}>대신 지금 보고 계신 기기의 카메라로
                    낙상 감지를 직접 체험해 보실 수 있습니다.</b>
                  ) : (
                    <b style={{ color: color.ink }}>전시 부스에 방문하시면 실시간 낙상 감지와
                    충격 완화 타일 작동을 직접 체험하실 수 있습니다.</b>
                  )}
                </p>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {selfAvailable && (
                <Button onClick={() => setStage("self")}
                        icon={<Video size={16} color={color.white} />}>
                  내 카메라로 체험하기
                </Button>
              )}
              <Button variant={selfAvailable ? "ghost" : undefined}
                      onClick={() => setStage("demo")}
                      icon={selfAvailable ? undefined : <Video size={16} color={color.white} />}>
                데모 영상 보기
              </Button>
              <Button variant="ghost" onClick={() => setStage("idle")}>다시 시도</Button>
            </div>

            {/* 개발·현장 진단. 무엇 때문에 못 붙었는지 화면에서 바로 보이게 한다.
                프로덕션 번들에서는 감춘다 — 온라인 관람객에게는 "uvicorn 이 8000
                포트에서 도는지 확인하세요" 같은 문장이 의미가 없고, 잘 만든 체험이
                갑자기 미완성처럼 보인다. 부스 노트북에서는 dev 서버로 띄우거나
                아래 URL 파라미터(?diag=1)로 켤 수 있다. */}
            {showDiag && (
            <details style={{ fontSize: font.caption, color: color.inkFaint }}>
              <summary style={{ cursor: "pointer" }}>
                연결 진단 (운영자용 — 관람객에게는 보이지 않습니다)
              </summary>
              <div style={{
                marginTop: 8, padding: 12, background: color.bg,
                borderRadius: radius.md, display: "flex",
                flexDirection: "column", gap: 5, lineHeight: 1.6,
              }}>
                <Row ok={diag.reachable}>서버 연결</Row>
                <Row ok={poseOn}>스켈레톤 수신 (WebSocket)</Row>
                <Row ok={diag.streaming}>
                  카메라 영상 수신 (누적 {diag.frames}프레임)
                </Row>
                <div style={{ marginTop: 6, color: color.inkSoft }}>
                  {!diag.reachable
                    ? "백엔드가 꺼져 있습니다. uvicorn 이 8000 포트에서 도는지 확인하세요."
                    : diag.frames === 0
                    ? "감지 파이프라인이 아직 아무것도 보내지 않았습니다. 터미널에서 실행하세요:\n" +
                      "python3 main.py 0 --no-serial --live-url http://localhost:8000"
                    : "프레임이 들어온 적은 있으나 지금은 멈춰 있습니다. main.py 가 종료되지 않았는지 확인하세요."}
                </div>
              </div>
            </details>
            )}
          </Card>

          <HowItConnects />
        </>
      )}

      {stage === "demo" && (
        <>
          {/* 영상이 들어오고 있는 카메라가 둘 이상일 때만 선택지를 보여준다.
              한 대뿐인데 탭이 있으면 고를 게 없는 선택지를 누르게 만든다. */}
          {diag.devices.length > 1 && (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: font.caption, color: color.inkFaint, marginRight: 4 }}>
                카메라
              </span>
              {diag.devices.map((d) => {
                const on = d === device;
                return (
                  <button key={d} onClick={() => setDevice(d)} style={{
                    padding: "5px 11px", fontSize: font.caption, fontWeight: 600,
                    borderRadius: 999, border: `1px solid ${on ? color.brand : color.line}`,
                    background: on ? color.brand : color.surface,
                    color: on ? color.white : color.inkSoft,
                  }}>
                    {cameraNames[d] ?? d}
                  </button>
                );
              })}
            </div>
          )}

          {/* 영상은 화면 높이에 맞춰 세우고, 안내가 그 옆을 채운다(ui/stage.ts). */}
          <div style={stageGrid(mobile)}>
          <Card pad={0} style={{ overflow: "hidden", ...mediaBox(mobile) }}>
            <div style={{ position: "relative", background: "#0E1116", height: "100%" }}>
              {on ? (
                // 캔버스에는 자세(스켈레톤)와 바닥 타일만 그린다. 카메라 원본은
                // 서버가 MJPEG 로 따로 들고 있고(진단용), 이 화면에는 얹지 않는다.
                <div style={{ position: "relative", lineHeight: 0, height: "100%" }}>
                  <canvas ref={canvasRef} width={480} height={720}
                          style={{
                            ...mediaFill,
                            opacity: paused ? 0.3 : 1,
                            transition: "opacity .2s",
                          }} />
                  {paused && (
                    <div style={{
                      position: "absolute", inset: 0,
                      display: "flex", flexDirection: "column",
                      alignItems: "center", justifyContent: "center", gap: 10,
                    }}>
                      <Pause size={30} color="rgba(255,255,255,0.7)" />
                      <div style={{ fontSize: font.small, color: "rgba(255,255,255,0.85)" }}>
                        카메라 연결을 끊었습니다
                      </div>
                      <div style={{ fontSize: font.caption, color: "rgba(255,255,255,0.5)" }}>
                        카메라가 해제되어 촬영하지 않습니다
                      </div>
                    </div>
                  )}
                </div>
              ) : videoBroken ? (
                // 영상 파일이 아직 없을 때(개발 중) 깨진 재생기 대신 안내를 보여준다.
                <div style={{
                  height: "100%", display: "flex",
                  flexDirection: "column", alignItems: "center", justifyContent: "center",
                  gap: 10, padding: 24, textAlign: "center",
                }}>
                  <Video size={30} color="rgba(255,255,255,0.5)" />
                  <div style={{ fontSize: font.small, color: "rgba(255,255,255,0.75)" }}>
                    데모 영상을 준비 중입니다
                  </div>
                  <div style={{ fontSize: font.caption, color: "rgba(255,255,255,0.45)" }}>
                    {DEMO_VIDEO_SRC}
                  </div>
                </div>
              ) : (
                // loop 를 뺐다 — 데모 영상은 낙상 장면 한 번을 보여주는 것이
                // 목적이라, 끝난 뒤 멈춰야 방금 본 장면을 이야기할 틈이 생긴다.
                <video src={DEMO_VIDEO_SRC} poster={DEMO_POSTER_SRC}
                       controls autoPlay muted playsInline
                       preload="metadata"
                       onError={() => setVideoBroken(true)}
                       style={mediaFill} />
              )}
              <div style={{ position: "absolute", left: 12, top: 12, display: "flex", gap: 6 }}>
                <Badge tone={paused ? "muted" : on ? "live" : "demo"}>
                  {paused ? "연결 끊김" : on ? "LIVE" : "데모 영상"}
                </Badge>
                <Badge tone="muted">{cameraPlaces[device] ?? cameraNames[device] ?? "카메라"}</Badge>
              </div>

              {on && (
                <button onClick={togglePause} disabled={pendingPause !== null}
                        aria-label={paused ? "카메라 다시 연결" : "카메라 연결 끊기"}
                        style={{
                          position: "absolute", right: 12, bottom: 12,
                          display: "flex", alignItems: "center", gap: 7,
                          padding: "8px 13px", borderRadius: 999,
                          background: "rgba(0,0,0,0.6)", color: color.white,
                          fontSize: font.caption, fontWeight: 600,
                          backdropFilter: "blur(4px)",
                          opacity: pendingPause !== null ? 0.6 : 1,
                        }}>
                  {paused ? <Play size={13} color={color.white} />
                          : <Pause size={13} color={color.white} />}
                  {pendingPause !== null ? "전환 중…"
                    : paused ? "카메라 다시 연결" : "카메라 잠시 끊기"}
                </button>
              )}
            </div>
          </Card>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {controlError && (
            <Card bg={color.redTint} style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <Alert size={16} color={color.red} />
              <span style={{ fontSize: font.small, color: color.red, fontWeight: 600 }}>
                {controlError}
              </span>
            </Card>
          )}

          {paused && (
            <Card bg={color.amberTint} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
              <Alert size={16} color={color.amber} />
              <span style={{ fontSize: font.small, color: color.ink, lineHeight: 1.6 }}>
                <b>카메라 연결이 끊긴 상태입니다.</b> 촬영과 낙상 감지가 모두 멈춰 있어,
                이 사이에 일어난 일은 기록되지 않습니다.
                다시 연결하면 몇 초 안에 화면이 돌아옵니다.
              </span>
            </Card>
          )}

          {on && !paused && (
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
          )}
          {!on && (
            <Card bg={color.brandTint} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
              <Wifi size={16} color={color.brand} />
              <span style={{ fontSize: font.small, color: color.ink, lineHeight: 1.6 }}>
                지금은 녹화된 데모 영상입니다.
                <br />
                <b>전시 부스에 방문하시면 카메라를 직접 연결해</b> 실시간 낙상 감지와
                타일 작동을 체험하실 수 있습니다.
              </span>
            </Card>
          )}

          </div>
          </div>
        </>
      )}
    </AppShell>
  );
}


/** 카메라가 어떻게 붙는지에 대한 설명. 관람객이 가장 많이 묻는 질문("와이파이인가요?
 *  블루투스인가요? 선을 꽂나요?")이라 '연결 실패' 화면에 붙여 둔다.
 *  개발 용어(WebSocket·파이프라인·포트·서버)는 한 글자도 쓰지 않는다. */
function HowItConnects() {
  const steps = [
    { n: "1", t: "카메라를 집 와이파이에 연결합니다",
      d: "다온 카메라는 인터넷(와이파이)으로 연결됩니다. 블루투스나 컴퓨터에 꽂는 선은 필요하지 않습니다." },
    { n: "2", t: "AI가 자세를 읽고 위험을 판단합니다",
      d: "사람이 지나가면 관절 위치를 알아보고, 넘어질 위험이 있는지 매 순간 판단합니다. 위험이 감지되면 넘어지는 방향의 타일이 즉시 펴집니다." },
    { n: "3", t: "이 화면에 자동으로 나타납니다",
      d: "연결된 카메라는 따로 설정하지 않아도 목록에 뜹니다. 앱에서 언제든 연결을 끊을 수 있습니다." },
  ];
  return (
    <Card style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <b style={{ fontSize: font.h2 }}>카메라는 어떻게 연결되나요?</b>
      {steps.map((s) => (
        <div key={s.n} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
          <span style={{
            width: 24, height: 24, flexShrink: 0, borderRadius: "50%",
            background: color.brandTint, color: color.brand,
            fontSize: font.caption, fontWeight: 700,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>{s.n}</span>
          <div>
            <div style={{ fontSize: font.small, fontWeight: 700 }}>{s.t}</div>
            <div style={{ fontSize: font.caption, color: color.inkSoft, lineHeight: 1.6 }}>
              {s.d}
            </div>
          </div>
        </div>
      ))}
    </Card>
  );
}

function Row({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
      <span style={{
        width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
        background: ok ? color.green : color.red,
      }} />
      <span style={{ color: ok ? color.ink : color.inkSoft }}>{children}</span>
    </div>
  );
}

function Badge({ tone, children }: { tone: "live" | "demo" | "muted"; children: React.ReactNode }) {
  const skin = {
    live: { background: color.red, color: color.white },
    demo: { background: color.brand, color: color.white },
    muted: { background: "rgba(0,0,0,0.55)", color: color.white },
  }[tone];
  return (
    <span style={{
      ...skin, padding: "3px 9px", fontSize: font.caption, fontWeight: 700,
      borderRadius: radius.sm, letterSpacing: 0.2,
    }}>
      {children}
    </span>
  );
}

function Spinner({ size = 26 }: { size?: number }) {
  return (
    <span style={{
      width: size, height: size, borderRadius: "50%",
      border: `2.5px solid ${color.brandTint2}`, borderTopColor: color.brand,
      animation: "daon-spin .8s linear infinite", display: "inline-block",
    }} />
  );
}
