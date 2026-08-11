import { useState, type FormEvent, type ChangeEvent, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { login, type User } from "../api";
import { setFlag, TOUR_SEEN } from "../storage";
import { color, font, radius, shadow } from "../theme";
import Logo from "../ui/Logo";
import Card from "../ui/Card";
import Button from "../ui/Button";

// 게스트 체험이 붙는 데모 계정. 관람객은 이메일을 입력하지 않고, 이 계정으로
// 조용히 로그인해 관리자 시점 전체를 둘러본다.
// ⚠️ webservice/seed.py 의 ADMIN_EMAIL/ADMIN_PW 와 반드시 같아야 한다.
//    예전에 어르신·보호자 두 계정을 쓰다가 관리자 단일 계정으로 바꾸면서
//    이 값이 뒤처져 체험 버튼이 통째로 죽은 적이 있다.
const GUEST = { email: "admin@daon.com", password: "pw" };

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
  //
  // '봤음' 플래그는 여기서 지운다. 같은 브라우저로 두 번째 관람객이 들어오면
  // 플래그가 남아 있어 안내가 건너뛰어진다 — 체험 진입은 항상 새 관람객으로
  // 취급해 첫 안내를 반드시 보여준다. (건너뛰기는 안내 안에서 여전히 가능)
  const guest = () => { setFlag(TOUR_SEEN, ""); go(GUEST.email, GUEST.password, "/consulting"); };

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
          {/* 첫 화면이라 워드마크를 헤더보다 크게 쓴다. */}
          <Logo height={30} />
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
