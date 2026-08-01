import { useState, type FormEvent, type ChangeEvent, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { login, type User } from "../api";
import { color, edge } from "../theme";
import { Shield } from "../ui/icons";
import Card from "../ui/Card";
import Button from "../ui/Button";

const inputStyle: CSSProperties = { padding: 12, background: color.white, fontSize: 16, ...edge(2) };

export default function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [email, setEmail] = useState("senior@daon.com");
  const [password, setPassword] = useState("pw");
  const [error, setError] = useState("");
  const nav = useNavigate();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      onLogin(await login(email, password));
      nav("/mypage");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div style={{ minHeight: "100%", background: color.bg, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <Card style={{ width: "100%", maxWidth: 360, display: "flex", flexDirection: "column", gap: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Shield size={26} />
          <span style={{ fontSize: 22, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.3 }}>Safety Advisor</span>
        </div>
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <input style={inputStyle} value={email} placeholder="이메일"
                 onChange={(e: ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)} />
          <input style={inputStyle} type="password" value={password} placeholder="비밀번호"
                 onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)} />
          <Button type="submit" full big>로그인</Button>
        </form>
        {error && <p style={{ color: color.red, margin: 0, fontWeight: 700 }}>{error}</p>}
      </Card>
    </div>
  );
}
