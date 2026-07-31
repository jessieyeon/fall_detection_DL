import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { analyzeVideo, consultingStatus, consultingReport,
         consultingReports, consultingImageUrl } from "../api.js";

export default function Consulting() {
  const [reports, setReports] = useState([]);
  const [active, setActive] = useState(null);   // {id, summary, findings}
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadList = () => consultingReports().then(setReports).catch(() => {});
  useEffect(() => { loadList(); }, []);

  async function open(rid) {
    setActive(await consultingReport(rid));
  }

  async function upload(e) {
    const file = e.target.files[0];
    if (!file) return;
    setError(""); setBusy(true); setActive(null);
    try {
      const { job_id } = await analyzeVideo(file);
      // 완료까지 폴링
      for (let i = 0; i < 120; i++) {
        const st = await consultingStatus(job_id);
        if (st.status === "done") { await open(st.report_id); await loadList(); break; }
        if (st.status === "error") { setError("분석 실패: " + st.error); break; }
        await new Promise((res) => setTimeout(res, 1000));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 720 }}>
      <h1>컨설팅</h1>
      <Link to="/mypage">← 마이페이지</Link>
      <div style={{ margin: "16px 0" }}>
        <label>집 생활 영상 업로드: </label>
        <input type="file" accept="video/*" onChange={upload} disabled={busy} />
        {busy && <span> 분석 중…</span>}
        {error && <p style={{ color: "crimson" }}>{error}</p>}
      </div>

      {active && (
        <div style={{ border: "1px solid #ccc", padding: 16, marginBottom: 16 }}>
          <img src={consultingImageUrl(active.id)} alt="히트맵"
               style={{ maxWidth: "100%" }} />
          <p><b>{active.summary}</b></p>
          <ul>
            {active.findings.map((f, i) => (
              <li key={i}>[{f.level}] {f.zone}: {f.recommendation}</li>
            ))}
          </ul>
        </div>
      )}

      <h2>지난 리포트</h2>
      <ul>
        {reports.map((r) => (
          <li key={r.id}>
            <button onClick={() => open(r.id)}>#{r.id}</button> {r.summary}
          </li>
        ))}
      </ul>
    </div>
  );
}
