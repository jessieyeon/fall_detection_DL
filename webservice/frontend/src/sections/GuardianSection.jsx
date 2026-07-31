import React, { useEffect, useState } from "react";
import { makeCode, redeemCode, wards, guardianList } from "../api.js";

export default function GuardianSection({ role }) {
  const [code, setCode] = useState("");
  const [input, setInput] = useState("");
  const [people, setPeople] = useState([]);
  const [error, setError] = useState("");

  const load = () =>
    (role === "guardian" ? wards() : guardianList()).then(setPeople).catch(() => {});
  useEffect(() => { load(); }, [role]);

  async function gen() { setCode((await makeCode()).code); }
  async function join() {
    setError("");
    try { await redeemCode(input); setInput(""); load(); }
    catch (e) { setError(e.message); }
  }

  return (
    <section style={{ marginTop: 24 }}>
      <h2>보호자 매칭</h2>
      {role === "senior" && (
        <div>
          <button onClick={gen}>연결 코드 생성</button>
          {code && <p>보호자에게 이 코드를 알려주세요: <b>{code}</b></p>}
          <p>연결된 보호자: {people.map((p) => p.name).join(", ") || "없음"}</p>
        </div>
      )}
      {role === "guardian" && (
        <div>
          <input value={input} onChange={(e) => setInput(e.target.value)}
                 placeholder="6자리 코드" />
          <button onClick={join}>연결</button>
          {error && <p style={{ color: "crimson" }}>{error}</p>}
          <ul>
            {people.map((p) => (
              <li key={p.id}>{p.name} — 자가진단 등급: {p.risk_level || "미실시"}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
