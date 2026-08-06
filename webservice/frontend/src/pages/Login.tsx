import { useState, type FormEvent, type ChangeEvent, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { login, type User } from "../api";
import { color, font, radius, shadow } from "../theme";
import { Shield } from "../ui/icons";
import Card from "../ui/Card";
import Button from "../ui/Button";

// 게스트 체험이 붙는 데모 계정. 보호자 시점을 보여주는 것이 컨셉이라 guardian.
const GUEST = { email: "guardian@daon.com", password: "pw" };

const inputStyle: CSSProperties = {
  padding: "10px 12px",
  background: color.white,
  fontSize: font.body,
  color: color.ink,
  border: `1px solid ${color.lineStrong}`,
  borderRadius: radius.md,
  outline: "none",
};

export default function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [email, setEmail] = useState(GUEST.email);
  const [password, setPassword] = useState(GUEST.password);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const nav = useNavigate();

  async function go(mail: string, pw: string, to: string) {
    setError("");
    setBusy(true);
    try {
      onLogin(await login(mail, pw));
      nav(to);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const submit = (e: FormEvent) => { e.preventDefault(); go(email, password, "/mypage"); };

  // 온라인 전시 관람객이 로그인 화면에서 막히면 체험 자체가 무산된다.
  // 게스트 버튼을 첫 화면의 주 동선으로 두고, 컨설팅으로 바로 보낸다.
  const guest = () => go(GUEST.email, GUEST.password, "/consulting");

  return (
    <div style={{
      minHeight: "100%", background: color.bg,
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: 20,
    }}>
      <Card raised style={{
        width: "100%", maxWidth: 380, padding: 26,
        display: "flex", flexDirection: "column", gap: 20,
      }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{
              width: 32, height: 32, borderRadius: 9, background: color.brand,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <Shield size={18} color={color.white} />
            </span>
            <span style={{ fontSize: font.h1, fontWeight: 700, letterSpacing: -0.3 }}>
              다온 안전지킴이
            </span>
          </div>
          <p style={{ margin: 0, fontSize: font.small, color: color.inkSoft, lineHeight: 1.6 }}>
            생활 영상으로 집 안 동선을 분석해 낙상 위험 구역을 찾아드립니다.
          </p>
        </div>

        <Button big full onClick={guest} disabled={busy}
                style={{ boxShadow: shadow.brand }}>
          {busy ? "준비 중…" : "체험하기"}
        </Button>
        <p style={{
          margin: "-12px 0 0", fontSize: font.caption, color: color.inkFaint,
          textAlign: "center",
        }}>
          가입 없이 바로 둘러볼 수 있어요
        </p>

        {error && (
          <p style={{ margin: 0, color: color.red, fontSize: font.small, fontWeight: 600 }}>
            {error}
          </p>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ flex: 1, height: 1, background: color.line }} />
          <span style={{ fontSize: font.caption, color: color.inkFaint }}>또는</span>
          <span style={{ flex: 1, height: 1, background: color.line }} />
        </div>

        {!showForm ? (
          <Button variant="ghost" full onClick={() => setShowForm(true)}>
            계정으로 로그인
          </Button>
        ) : (
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <input style={inputStyle} value={email} placeholder="이메일" autoComplete="username"
                   onChange={(e: ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)} />
            <input style={inputStyle} type="password" value={password} placeholder="비밀번호"
                   autoComplete="current-password"
                   onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)} />
            <Button variant="outline" type="submit" full disabled={busy}>로그인</Button>
          </form>
        )}
      </Card>
    </div>
  );
}
