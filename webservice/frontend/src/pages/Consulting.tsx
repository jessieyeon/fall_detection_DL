import { useEffect, useState, type ChangeEvent } from "react";
import {
  analyzeVideo, consultingStatus, consultingReport, consultingReports,
  consultingImageUrl, type Report, type ReportRow,
} from "../api";
import { color, edge } from "../theme";
import { Video, Alert, Chevron, Help } from "../ui/icons";
import AppShell from "../ui/AppShell";
import Section from "../ui/Section";
import Card from "../ui/Card";
import Button from "../ui/Button";

const levelColor = (lvl?: string) => (lvl === "높음" ? color.red : lvl === "보통" ? "#B4690E" : color.gray);

export default function Consulting() {
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [active, setActive] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showList, setShowList] = useState(false);

  const loadList = () => consultingReports().then(setReports).catch(() => {});
  const open = async (rid: number) => setActive(await consultingReport(rid));

  useEffect(() => {
    consultingReports().then((rows) => {
      setReports(rows);
      if (rows[0]) open(rows[0].id);
    }).catch(() => {});
  }, []);

  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(""); setBusy(true); setActive(null);
    try {
      const { job_id } = await analyzeVideo(file);
      for (let i = 0; i < 120; i++) {
        const st = await consultingStatus(job_id);
        if (st.status === "done" && st.report_id != null) { await open(st.report_id); await loadList(); break; }
        if (st.status === "error") { setError("분석 실패: " + st.error); break; }
        await new Promise((r) => setTimeout(r, 1000));
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const top = active?.findings[0];

  return (
    <AppShell active="consult" right={<Help size={20} />}>
      {/* 업로드 */}
      <Section divider={false} gap={16}>
        <Button as="label" big full icon={<Video color="white" />}>
          {busy ? "분석 중…" : "Upload Home Video"}
          <input type="file" accept="video/*" hidden disabled={busy} onChange={upload} />
        </Button>
        <p style={{ margin: 0, textAlign: "center", color: color.gray, fontSize: 16 }}>
          집 생활 영상을 올리면 전문 안전 분석 리포트를 만들어 드립니다.
        </p>
        {error && <p style={{ margin: 0, color: color.red, fontWeight: 700 }}>{error}</p>}
      </Section>

      {/* 최신 분석 결과 */}
      <Section title="LATEST ANALYSIS RESULT" gap={16}>
        {!active && <p style={{ margin: 0, color: color.gray }}>아직 분석 결과가 없습니다. 영상을 업로드해 보세요.</p>}
        {active && (
          <Card pad={0} style={{ overflow: "hidden" }}>
            <div style={{ position: "relative", borderBottom: `2px solid ${color.black}` }}>
              <img src={consultingImageUrl(active.id)} alt="히트맵" style={{ display: "block", width: "100%" }} />
              {top && (
                <div style={{ position: "absolute", left: 16, top: 16, display: "flex", alignItems: "center", gap: 8, background: levelColor(top.level), color: color.white, padding: "8px 12px", ...edge(2) }}>
                  <Alert size={18} color="white" />
                  <span style={{ fontSize: 15, fontWeight: 700, textTransform: "uppercase" }}>{top.level} RISK</span>
                </div>
              )}
            </div>
            <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
              <h3 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: color.red, textTransform: "uppercase" }}>낙상 위험 감지</h3>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: 0.3 }}>WHY IT&apos;S A HAZARD:</div>
                <p style={{ margin: "4px 0 0", fontSize: 18, fontWeight: 700, lineHeight: 1.5 }}>{active.summary}</p>
              </div>
              {active.findings.map((f, i) => (
                <div key={i} style={{ background: color.blue2, padding: 16, ...edge(2) }}>
                  <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: 0.3 }}>RECOMMENDED FIX · {f.zone}</div>
                  <p style={{ margin: "6px 0 0", fontSize: 18, fontWeight: 700, lineHeight: 1.5 }}>{f.recommendation}</p>
                </div>
              ))}
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
              <div style={{ fontWeight: 700 }}>#{r.id}</div>
              <div style={{ color: color.gray, fontSize: 15 }}>{r.summary}</div>
            </Card>
          ))}
        </Section>
      )}
    </AppShell>
  );
}
