import React, { useState } from "react";
import { hospitals as fetchHospitals, floorplanUrl } from "../api.js";

export default function HomeSection({ apartment }) {
  const [list, setList] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try { setList(await fetchHospitals()); }
    catch (e) { setError(e.message); }
  }

  return (
    <section style={{ marginTop: 24 }}>
      <h2>우리 집</h2>
      {apartment
        ? <img src={floorplanUrl(apartment)} alt="평면도"
               style={{ maxWidth: "100%", border: "1px solid #ccc" }}
               onError={(e) => { e.target.style.display = "none"; }} />
        : <p>등록된 아파트가 없습니다.</p>}
      <div style={{ marginTop: 12 }}>
        <button onClick={load}>근처 병원 찾기</button>
        {error && <p style={{ color: "crimson" }}>{error}</p>}
        {list && (
          <ul>
            {list.map((h, i) => (
              <li key={i}>{h.name} ({h.distance_m}m) {h.phone}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
