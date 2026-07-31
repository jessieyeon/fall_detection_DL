import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api.js";

export default function Login({ onLogin }) {
  const [email, setEmail] = useState("senior@daon.com");
  const [password, setPassword] = useState("pw");
  const [error, setError] = useState("");
  const nav = useNavigate();

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      onLogin(await login(email, password));
      nav("/mypage");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form onSubmit={submit} style={{ padding: 24, maxWidth: 320 }}>
      <h1>다온 로그인</h1>
      <input value={email} onChange={(e) => setEmail(e.target.value)}
             placeholder="이메일" style={{ display: "block", width: "100%", marginBottom: 8 }} />
      <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
             placeholder="비밀번호" style={{ display: "block", width: "100%", marginBottom: 8 }} />
      <button type="submit">로그인</button>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
    </form>
  );
}
