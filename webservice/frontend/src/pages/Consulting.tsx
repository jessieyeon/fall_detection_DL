import { useEffect, useRef, useState, type ChangeEvent } from "react";
import {
  analyzeVideo, consultingStatus, consultingReport, consultingReports,
  consultingImageUrl, type Report, type ReportRow,
} from "../api";
import { color, font, radius } from "../theme";
import { useIsMobile } from "../useMedia";
import { notifyDone, primeNotifications, stopTitleFlash } from "../notify";
import { getFlag, setFlag } from "../storage";
import { Video, Alert, Check, Chevron } from "../ui/icons";
import AppShell from "../ui/AppShell";
import Section from "../ui/Section";
import Card from "../ui/Card";
import Button from "../ui/Button";
import Tour from "../ui/Tour";

const TOUR_SEEN = "daon.tour.seen";

/**
 * 체험용 샘플 영상. 파일은 webservice/frontend/public/samples/ 에 둔다.
 * 온라인 관람객은 집 영상을 갖고 있지 않으므로 이걸 바로 고를 수 있어야 한다.
 */
const SAMPLES = [
  { id: "bedroom", label: "안방", desc: "화장실을 오가는 야간 동선", file: "/samples/bedroom.mp4" },
  { id: "living", label: "거실", desc: "가장 자주 지나다니는 공간", file: "/samples/living.mp4" },
  { id: "kitchen", label: "부엌", desc: "조리 중 반복되는 짧은 이동", file: "/samples/kitchen.mp4" },
];

const ROOMS = ["거실", "안방", "부엌", "화장실", "현관", "기타"];

const levelSkin = (lvl?: string) =>
  lvl === "높음" ? { fg: color.red, bg: color.redTint }
  : lvl === "보통" ? { fg: color.amber, bg: color.amberTint }
  : { fg: color.inkSoft, bg: color.bg };

const STEPS = ["영상 업로드", "사람 인식", "동선 추출", "위험 구역 판정"];

export default function Consulting() {
  const mobile = useIsMobile();
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [active, setActive] = useState<Report | null>(null);
  const [room, setRoom] = useState("거실");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  // 실패한 단계 번호. null 이 아니면 진행 바가 그 단계에서 빨갛게 멈춘다.
  const [failedStep, setFailedStep] = useState<number | null>(null);
  const stepRef = useRef(0);
  const [error, setError] = useState("");
  const [justDone, setJustDone] = useState(false);
  const [showList, setShowList] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);
  const [ready, setReady] = useState<Set<string> | null>(null);   // null=확인 중
  const [showTour, setShowTour] = useState(() => getFlag(TOUR_SEEN) !== "1");
  const [sampleTab, setSampleTab] = useState<string>(SAMPLES[0].id);

  const closeTour = () => { setShowTour(false); setFlag(TOUR_SEEN, "1"); };

  const loadList = () => consultingReports().then(setReports).catch(() => {});
  const open = async (rid: number) => setActive(await consultingReport(rid));

  useEffect(() => {
    consultingReports()
      .then((rows) => { setReports(rows); if (rows[0]) open(rows[0].id); })
      .catch(() => {});
    return stopTitleFlash;
  }, []);

  // 샘플 영상이 실제로 있는지 미리 확인한다. 없는 카드를 눌러보고 나서
  // 실패를 보는 것보다, 애초에 '준비 중'으로 보여주는 편이 낫다.
  // 주의: SPA 는 없는 경로에도 index.html 을 200으로 돌려주므로 상태코드만으로는
  // 부족하다 — content-type 이 video 인지까지 봐야 한다.
  useEffect(() => {
    let alive = true;
    Promise.all(SAMPLES.map((s) =>
      fetch(s.file, { method: "HEAD" })
        .then((r) => {
          const type = r.headers.get("content-type") ?? "";
          return r.ok && type.startsWith("video") ? s.id : null;
        })
        .catch(() => null)
    )).then((ids) => {
      if (alive) setReady(new Set(ids.filter(Boolean) as string[]));
    });
    return () => { alive = false; };
  }, []);

  // 진행 단계는 연출이다. 실제 분석은 3~5초라 서버가 단계를 알려주지 않는다.
  useEffect(() => {
    if (!busy) return;
    const id = setInterval(() => setStep((s) => {
      const next = Math.min(s + 1, STEPS.length - 1);
      stepRef.current = next;
      return next;
    }), 900);
    return () => clearInterval(id);
  }, [busy]);

  /** 실패 처리: 원인 단계에서 진행 바를 빨갛게 멈추고, 사람이 읽을 문장만 보여준다.
   *  서버가 주는 ffmpeg 로그 따위는 화면에 흘리지 않는다(콘솔에만 남긴다). */
  function fail(rawMessage: string) {
    console.error("[분석 실패]", rawMessage);
    // 파일을 읽지 못한 실패는 시작 단계(영상 업로드)의 문제다
    const early = /변환|업로드|moov|열 수 없|Invalid data|읽을 수 없/i.test(rawMessage);
    const at = early ? 0 : stepRef.current;
    setStep(at);
    setFailedStep(at);
    setError(early
      ? "영상 파일을 읽을 수 없어 분석을 시작하지 못했습니다."
      : "분석 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.");
  }

  async function run(file: File, label: string) {
    setError(""); setJustDone(false); setActive(null);
    setStep(0); stepRef.current = 0; setFailedStep(null); setBusy(true);
    primeNotifications();          // 사용자 제스처 안에서 권한을 물어둔다
    try {
      const { job_id } = await analyzeVideo(file, label);
      for (let i = 0; i < 300; i++) {
        const st = await consultingStatus(job_id);
        if (st.status === "done" && st.report_id != null) {
          setStep(STEPS.length - 1);
          await open(st.report_id);
          await loadList();
          setJustDone(true);
          notifyDone("분석이 완료되었습니다", `${label} 영상의 낙상 위험 리포트가 준비됐어요.`);
          return;
        }
        if (st.status === "error") { fail(st.error ?? "unknown"); return; }
        await new Promise((r) => setTimeout(r, 1000));
      }
      await loadList();
      setError("분석이 오래 걸리고 있어요. 완료되면 아래 '지난 결과'에 표시됩니다.");
    } catch (err) {
      fail((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    await run(file, room);
    e.target.value = "";           // 같은 파일을 다시 고를 수 있게
  }

  async function useSample(s: (typeof SAMPLES)[number]) {
    setError(""); setFailedStep(null); setBusy(true);
    try {
      const res = await fetch(s.file);
      const blob = await res.blob();
      // SPA 폴백이 index.html 을 200으로 주므로, 진짜 영상인지 타입으로 확인한다.
      // HTML 조각을 mp4 로 올리면 서버 ffmpeg 에서야 터진다 — 여기서 끊는 게 맞다.
      if (!res.ok || !blob.type.startsWith("video")) {
        throw new Error("샘플 영상을 아직 준비 중입니다");
      }
      setBusy(false);
      await run(new File([blob], `${s.id}.mp4`, { type: "video/mp4" }), s.label);
    } catch (err) {
      setBusy(false);
      fail((err as Error).message);
    }
  }

  const top = active?.findings[0];

  return (
    <AppShell active="consult">
      <div style={{
        display: "flex", justifyContent: "space-between",
        alignItems: "flex-start", gap: 12,
      }}>
        <h1 style={{ margin: 0, fontSize: font.h1, fontWeight: 700 }}>동선 컨설팅</h1>
        <button onClick={() => setShowTour(true)} style={{
          flexShrink: 0, fontSize: font.caption, color: color.brand,
          fontWeight: 600, padding: "3px 8px",
        }}>
          앱 소개
        </button>
      </div>

      {showTour && <Tour onClose={closeTour} />}

      {/* 샘플 선택 — 탭으로 방을 고르고, 영상을 직접 본 뒤 분석을 누른다.
          무엇을 분석하는지 눈으로 확인한 다음 결과를 봐야 체험이 이해된다. */}
      <Section title="체험용">
        <Card pad={0} data-tour="samples" style={{ overflow: "hidden" }}>
          <div style={{ display: "flex", borderBottom: `1px solid ${color.line}` }}>
            {SAMPLES.map((s) => {
              const on = s.id === sampleTab;
              return (
                <button key={s.id} onClick={() => setSampleTab(s.id)} style={{
                  flex: 1, padding: "11px 8px",
                  fontSize: font.small, fontWeight: on ? 700 : 500,
                  color: on ? color.brand : color.inkSoft,
                  borderBottom: `2px solid ${on ? color.brand : "transparent"}`,
                  background: on ? color.brandTint : "transparent",
                }}>
                  {s.label}
                </button>
              );
            })}
          </div>

          {(() => {
            const s = SAMPLES.find((x) => x.id === sampleTab)!;
            const available = ready === null || ready.has(s.id);
            return (
              <div style={{ display: "flex", flexDirection: "column" }}>
                {available ? (
                  <video key={s.id} src={s.file} controls muted loop playsInline
                         style={{ display: "block", width: "100%", maxHeight: 320,
                                  background: "#0E1116" }} />
                ) : (
                  <div style={{
                    height: 180, background: "#0E1116",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: font.small, color: "rgba(255,255,255,0.5)",
                  }}>
                    영상을 준비 중입니다
                  </div>
                )}
                <div style={{
                  padding: 14, display: "flex", alignItems: "center",
                  justifyContent: "space-between", gap: 12, flexWrap: "wrap",
                }}>
                  <span style={{ fontSize: font.caption, color: color.inkSoft }}>
                    {s.desc}
                  </span>
                  <Button disabled={busy || !available} onClick={() => useSample(s)}>
                    {available ? "이 영상 분석하기" : "준비 중"}
                  </Button>
                </div>
              </div>
            );
          })()}
        </Card>
      </Section>

      {/* 직접 업로드 */}
      <Section title="내 영상 올리기">
        <Card style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <div style={{ fontSize: font.caption, color: color.inkFaint, marginBottom: 6 }}>
              촬영 위치
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {ROOMS.map((r) => (
                <button key={r} onClick={() => setRoom(r)} style={{
                  padding: "5px 11px", fontSize: font.caption, fontWeight: 600,
                  borderRadius: 999,
                  border: `1px solid ${room === r ? color.brand : color.line}`,
                  background: room === r ? color.brand : color.surface,
                  color: room === r ? color.white : color.inkSoft,
                }}>
                  {r}
                </button>
              ))}
            </div>
          </div>
          <Button as="label" full disabled={busy}
                  icon={<Video size={16} color={color.white} />}
                  style={{ cursor: busy ? "not-allowed" : "pointer" }}>
            {busy ? "분석 중…" : "영상 선택"}
            <input type="file" accept="video/*" hidden disabled={busy} onChange={upload} />
          </Button>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {[
              "천장 모서리에 고정한 카메라로 촬영한 영상일 때 가장 정확합니다.",
              "손에 들고 찍으면 구역 판정이 어긋납니다.",
            ].map((t, i) => (
              <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <span style={{
                  flexShrink: 0, width: 16, height: 16, borderRadius: "50%",
                  background: color.brandTint, color: color.brand,
                  fontSize: 10, fontWeight: 700, marginTop: 1,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  {i + 1}
                </span>
                <span style={{ fontSize: font.caption, color: color.inkSoft, lineHeight: 1.6 }}>
                  {t}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </Section>

      {(busy || failedStep !== null) && (
        <Progress step={step} failed={failedStep !== null} />
      )}

      {error && (
        <Card bg={color.redTint} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
          <Alert size={16} color={color.red} />
          <span style={{ fontSize: font.small, color: color.red, fontWeight: 600 }}>{error}</span>
        </Card>
      )}

      {justDone && (
        <Card bg={color.greenTint} style={{
          display: "flex", gap: 10, alignItems: "center", justifyContent: "space-between",
        }}>
          <span style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <Check size={16} color={color.green} />
            <span style={{ fontSize: font.small, color: color.green, fontWeight: 700 }}>
              분석이 완료되었습니다
            </span>
          </span>
          <button onClick={() => setJustDone(false)}
                  style={{ fontSize: font.caption, color: color.inkFaint }}>
            닫기
          </button>
        </Card>
      )}

      {/* 결과 */}
      {active && (
        <Section title="분석 결과"
                 hint={active.location ? `촬영 위치 · ${active.location}` : undefined}>
          <div style={{
            display: "grid", gap: 14,
            gridTemplateColumns: mobile ? "1fr" : "minmax(0,1.35fr) minmax(0,1fr)",
            alignItems: "start",
          }}>
            <Card pad={0} style={{ overflow: "hidden" }}>
              <img src={consultingImageUrl(active.id)} alt="이동 동선"
                   style={{ display: "block", width: "100%" }} />
              <div style={{
                display: "flex", gap: 14, flexWrap: "wrap",
                padding: "10px 14px", borderTop: `1px solid ${color.line}`,
                fontSize: font.caption, color: color.inkSoft,
              }}>
                <Legend dot="#2DA52E">시작</Legend>
                <Legend dot="#E13C3C">끝</Legend>
                <Legend dot="#F59100">방향 전환</Legend>
                <Legend dot={color.brand}>이동 경로</Legend>
              </div>
            </Card>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {top && (
                <Card style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <span style={{
                    alignSelf: "flex-start", padding: "3px 10px", borderRadius: 999,
                    fontSize: font.caption, fontWeight: 700,
                    color: levelSkin(top.level).fg, background: levelSkin(top.level).bg,
                  }}>
                    낙상 위험 {top.level}
                  </span>
                  <div style={{ fontSize: font.h2, fontWeight: 700 }}>{top.zone} 구역</div>
                  <p style={{ margin: 0, fontSize: font.small, color: color.inkSoft, lineHeight: 1.7 }}>
                    {active.summary}
                  </p>
                </Card>
              )}
              {top && (
                <Card bg={color.brandTint} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div style={{ fontSize: font.caption, fontWeight: 700, color: color.brand }}>
                    권장 개선 방법
                  </div>
                  <p style={{ margin: 0, fontSize: font.small, lineHeight: 1.7 }}>
                    {top.recommendation}
                  </p>
                </Card>
              )}
              {active.evidence && (
                // 근거는 궁금할 때만 펼쳐 본다 — 리포트의 주인공은 권고이지 출처가 아니다.
                !showEvidence ? (
                  <button onClick={() => setShowEvidence(true)} style={{
                    alignSelf: "flex-start", fontSize: font.caption,
                    color: color.brand, fontWeight: 600,
                    padding: "6px 10px", borderRadius: radius.sm,
                    border: `1px solid ${color.line}`, background: color.surface,
                  }}>
                    근거 보기
                  </button>
                ) : (
                  <Card style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <div style={{
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                    }}>
                      <span style={{ fontSize: font.caption, fontWeight: 700, color: color.inkFaint }}>
                        근거
                      </span>
                      <button onClick={() => setShowEvidence(false)}
                              style={{ fontSize: font.caption, color: color.inkFaint }}>
                        접기
                      </button>
                    </div>
                    <p style={{ margin: 0, fontSize: font.caption, color: color.inkSoft, lineHeight: 1.7 }}>
                      {active.evidence}
                    </p>
                  </Card>
                )
              )}
            </div>
          </div>
        </Section>
      )}

      {!active && !busy && (
        <Card style={{ textAlign: "center", padding: "30px 20px" }}>
          <p style={{ margin: 0, fontSize: font.small, color: color.inkFaint }}>
            아직 분석 결과가 없습니다.
          </p>
        </Card>
      )}

      {reports.length > 0 && (
        <Section gap={8}>
          <button onClick={() => setShowList((v) => !v)}
                  style={{ width: "100%", textAlign: "left", padding: 0, background: "none" }}>
            <Card style={{
              display: "flex", alignItems: "center", justifyContent: "space-between", padding: 14,
            }}>
              <span style={{ fontSize: font.small, fontWeight: 600 }}>
                지난 결과 {reports.length}건
              </span>
              <span style={{ fontSize: font.caption, color: color.brand, fontWeight: 600 }}>
                {showList ? "접기" : "펼치기"}
              </span>
            </Card>
          </button>
          {showList && reports.map((r) => (
            <button key={r.id} onClick={() => open(r.id)}
                    style={{ width: "100%", textAlign: "left", padding: 0, background: "none" }}>
              <Card pad={12} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                <div style={{ fontSize: font.small, fontWeight: 600 }}>
                  {r.location || `리포트 #${r.id}`}
                </div>
                <div style={{
                  fontSize: font.caption, color: color.inkFaint,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>
                  {r.summary}
                </div>
              </Card>
            </button>
          ))}
        </Section>
      )}
    </AppShell>
  );
}

function Legend({ dot, children }: { dot: string; children: React.ReactNode }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      <span style={{
        width: 9, height: 9, borderRadius: "50%", background: dot,
        border: "1.5px solid #fff", boxShadow: "0 0 0 1px rgba(0,0,0,.12)",
      }} />
      {children}
    </span>
  );
}

function Progress({ step, failed }: { step: number; failed?: boolean }) {
  return (
    <Card raised style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {failed ? (
          // 실패: 스피너 대신 멈춘 빨간 표식. 어느 단계에서 끊겼는지가 남는다.
          <span style={{
            width: 18, height: 18, borderRadius: "50%", background: color.red,
            color: color.white, fontSize: 11, fontWeight: 700,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            ✕
          </span>
        ) : (
          <span style={{
            width: 18, height: 18, borderRadius: "50%",
            border: `2px solid ${color.brandTint2}`, borderTopColor: color.brand,
            animation: "daon-spin .8s linear infinite",
          }} />
        )}
        <span style={{
          fontSize: font.body, fontWeight: 600,
          color: failed ? color.red : color.ink,
        }}>
          {STEPS[step]}{failed && " 실패"}
        </span>
      </div>
      <div style={{
        height: 5, borderRadius: 999, overflow: "hidden",
        background: failed ? color.redTint : color.brandTint2,
      }}>
        <div style={{
          height: "100%", borderRadius: 999,
          background: failed ? color.red : color.brand,
          width: `${((step + 1) / STEPS.length) * 100}%`,
          transition: "width .5s ease",
        }} />
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {STEPS.map((s, i) => {
          const isFailPoint = failed && i === step;
          const reached = i <= step;
          return (
            <span key={s} style={{
              fontSize: font.caption, padding: "2px 8px", borderRadius: radius.sm,
              background: isFailPoint ? color.red
                : reached && !failed ? color.brandTint : "transparent",
              color: isFailPoint ? color.white
                : reached && !failed ? color.brand : color.inkFaint,
              fontWeight: i === step ? 700 : 500,
            }}>
              {s}
            </span>
          );
        })}
      </div>
    </Card>
  );
}
