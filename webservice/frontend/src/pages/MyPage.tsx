import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { logout, redeemCode, wards, type User, type Ward } from "../api";
import { color, edge } from "../theme";
import { Check } from "../ui/icons";
import AppShell from "../ui/AppShell";
import Section from "../ui/Section";
import Card from "../ui/Card";
import Button from "../ui/Button";

const levelColor = (lvl?: string | null) => (lvl === "높음" ? color.red : lvl === "보통" ? "#B4690E" : color.gray);

function AccountCard({ user, onLogout }: { user: User; onLogout: () => void }) {
  const nav = useNavigate();
  const doLogout = async () => { try { await logout(); } finally { onLogout(); nav("/login"); } };
  return (
    <Card style={{ display: "flex", alignItems: "center", gap: 20 }}>
      <div style={{ width: 56, height: 72, background: color.blue1, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28, fontWeight: 700, ...edge(2) }}>
        {user.name.slice(0, 1) || "?"}
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
        <div style={{ fontSize: 22, fontWeight: 700 }}>{user.name}</div>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8, alignSelf: "flex-start", background: color.black, color: color.white, padding: "4px 12px", fontSize: 14, fontWeight: 700 }}>
          <Check size={14} color="white" /> {user.role === "senior" ? "어르신" : "보호자"} · 로그인됨
        </span>
      </div>
      <Button variant="outline" onClick={doLogout}>로그아웃</Button>
    </Card>
  );
}

export default function MyPage({ user, onLogout }: { user: User; onLogout: () => void }) {
  return user.role === "guardian"
    ? <GuardianHome user={user} onLogout={onLogout} />
    : <SeniorHome user={user} onLogout={onLogout} />;
}

function SeniorHome({ user, onLogout }: { user: User; onLogout: () => void }) {
  return (
    <AppShell active="mypage">
      <Section title="내 계정" divider={false}>
        <AccountCard user={user} onLogout={onLogout} />
      </Section>
    </AppShell>
  );
}

function GuardianHome({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [linked, setLinked] = useState<Ward[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");

  const load = () => wards().then(setLinked).catch(() => {});
  useEffect(() => { load(); }, []);

  async function join() {
    setError("");
    try { await redeemCode(input); setInput(""); load(); }
    catch (e) { setError((e as Error).message); }
  }

  return (
    <AppShell active="mypage">
      <Section title="내 계정" divider={false}>
        <AccountCard user={user} onLogout={onLogout} />
      </Section>

      <Section title="연결된 어르신">
        {linked.length === 0 && <p style={{ margin: 0, color: color.gray }}>아직 연결된 어르신이 없습니다. 아래에서 코드로 연결하세요.</p>}
        {linked.map((w) => (
          <Card key={w.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{w.name}</div>
            <span style={{ padding: "4px 12px", fontWeight: 700, color: color.white, background: levelColor(w.risk_level) }}>
              {w.risk_level ? `위험도 ${w.risk_level}` : "자가진단 미실시"}
            </span>
          </Card>
        ))}
      </Section>

      <Section title="어르신 연결">
        <Card style={{ display: "flex", gap: 12 }}>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="6자리 코드"
                 style={{ flex: 1, padding: 12, fontSize: 16, ...edge(2) }} />
          <Button onClick={join}>연결</Button>
        </Card>
        {error && <p style={{ margin: 0, color: color.red, fontWeight: 700 }}>{error}</p>}
      </Section>
    </AppShell>
  );
}
