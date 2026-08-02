import { useEffect, useState, type ChangeEvent } from "react";
import {
  analyzeVideo, consultingStatus, consultingReport, consultingReports,
  consultingImageUrl, type Report, type ReportRow,
} from "../api";
import { color, edge } from "../theme";
import { Video, Alert, Chevron } from "../ui/icons";
import AppShell from "../ui/AppShell";
import Section from "../ui/Section";
import Card from "../ui/Card";
import Button from "../ui/Button";

const ROOMS = ["거실", "침실", "주방", "화장실", "현관", "기타"];
const levelColor = (lvl?: string) => (lvl === "높음" ? color.red : lvl === "보통" ? "#B4690E" : color.gray);

export default function Consulting() {
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [active, setActive] = useState<Report | null>(null);
  const [room, setRoom] = useState("거실");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showList, setShowList] = useState(false);

  const loadList = () => consultingReports().then(setReports).catch(() => {});
  const open = async (rid: number) => setActive(await consultingReport(rid));

  useEffect(() => {
    consultingReports().then((rows) => { setReports(rows); if (rows[0]) open(rows[0].id); }).catch(() => {});
  }, []);

  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(""); setBusy(true); setActive(null);
    try {
      const { job_id } = await analyzeVideo(file, room);
      let done = false;
      // CPU 에서 YOLO 분석이 오래 걸릴 수 있어 넉넉히 기다린다(최대 5분).
      for (let i = 0; i < 300; i++) {
        const st = await consultingStatus(job_id);
        if (st.status === "done" && st.report_id != null) { await open(st.report_id); await loadList(); done = true; break; }
        if (st.status === "error") { setError("분석에 실패했습니다: " + st.error); done = true; break; }
        await new Promise((r) => setTimeout(r, 1000));
      }
      if (!done) { await loadList(); setError("분석이 오래 걸리고 있어요. 완료되면 아래 '지난 결과'에 표시됩니다. 잠시 후 다시 확인해 주세요."); }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const top = active?.findings[0];   // 가장 위험한 구역 하나만 보여준다

  return (
    <AppShell active="consult">
      {/* 업로드 + 위치 선택 + 안내 */}
      <Section divider={false} gap={16}>
        <div>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>촬영 위치 선택</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {ROOMS.map((r) => (
              <button key={r} onClick={() => setRoom(r)}
                style={{ padding: "8px 14px", fontSize: 16, fontWeight: 700, ...edge(2),
                         background: room === r ? color.black : color.white, color: room === r ? color.white : color.ink }}>
                {r}
              </button>
            ))}
          </div>
        </div>

        <Button as="label" big full icon={<Video color="white" />}>
          {busy ? "분석 중입니다…" : "생활 영상 올리기"}
          <input type="file" accept="video/*" hidden disabled={busy} onChange={upload} />
        </Button>
        {error && <p style={{ margin: 0, color: color.red, fontWeight: 700 }}>{error}</p>}

        <Card bg={color.blue3} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[
            "위 '생활 영상 올리기' 버튼을 누르고, 집에서 생활하는 모습이 담긴 영상을 선택해 주세요.",
            "올린 영상을 인공지능이 분석해 낙상 위험이 있는 구역을 찾아냅니다. (30초~1분 정도 걸릴 수 있어요.)",
            "아래 '최근 분석 결과'에서 위험 구역과 개선 방법을 확인해 주세요.",
          ].map((t, i) => (
            <div key={i} style={{ display: "flex", gap: 12 }}>
              <div style={{ flexShrink: 0, width: 28, height: 28, background: color.black, color: color.white, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700 }}>{i + 1}</div>
              <div style={{ fontSize: 17, lineHeight: 1.5 }}>{t}</div>
            </div>
          ))}
        </Card>
      </Section>

      {/* 최근 분석 결과 */}
      <Section title="최근 분석 결과" gap={16}>
        {!active && <p style={{ margin: 0, color: color.gray }}>아직 분석 결과가 없습니다. 위에서 영상을 올려 주세요.</p>}
        {active && (
          <Card pad={0} style={{ overflow: "hidden" }}>
            {/* 캡처된 영상 프레임 위에 위험 구역이 빨갛게 표시된 히트맵 */}
            <div style={{ position: "relative", borderBottom: `2px solid ${color.black}` }}>
              <img src={consultingImageUrl(active.id)} alt="위험 구역 히트맵" style={{ display: "block", width: "100%" }} />
              {top && (
                <div style={{ position: "absolute", left: 16, top: 16, display: "flex", alignItems: "center", gap: 8, background: levelColor(top.level), color: color.white, padding: "8px 12px", ...edge(2) }}>
                  <Alert size={18} color="white" />
                  <span style={{ fontSize: 15, fontWeight: 700 }}>위험도 {top.level}</span>
                </div>
              )}
            </div>
            <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                <h3 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: color.red }}>낙상 위험이 감지되었습니다</h3>
                {active.location && <span style={{ color: color.gray, fontWeight: 700 }}>촬영 위치 · {active.location}</span>}
              </div>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700 }}>왜 위험한가요?</div>
                <p style={{ margin: "4px 0 0", fontSize: 18, lineHeight: 1.6 }}>{active.summary}</p>
              </div>
              {top && (
                <div style={{ background: color.blue2, padding: 16, ...edge(2) }}>
                  <div style={{ fontSize: 15, fontWeight: 700 }}>권장 개선 방법</div>
                  <p style={{ margin: "6px 0 0", fontSize: 18, lineHeight: 1.6 }}>{top.recommendation}</p>
                </div>
              )}
              <Button variant="outline" full>확인했어요</Button>
            </div>
          </Card>
        )}
      </Section>

      {/* 지난 결과 */}
      {reports.length > 0 && (
        <Section divider={false} gap={8}>
          <Card bg={color.blue3} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: 16, cursor: "pointer" }}
                onClick={() => setShowList((v) => !v)}>
            <span style={{ fontWeight: 700 }}>지난 결과 ({reports.length})</span>
            <Chevron size={16} />
          </Card>
          {showList && reports.map((r) => (
            <Card key={r.id} style={{ padding: 12, cursor: "pointer" }} onClick={() => open(r.id)}>
              <div style={{ fontWeight: 700 }}>{r.location || `리포트 #${r.id}`}</div>
              <div style={{ color: color.gray, fontSize: 15 }}>{r.summary}</div>
            </Card>
          ))}
        </Section>
      )}
    </AppShell>
  );
}
