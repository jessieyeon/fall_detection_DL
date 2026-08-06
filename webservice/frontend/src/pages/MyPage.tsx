import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { logout, redeemCode, wards, type User, type Ward } from "../api";
import { color, font, radius } from "../theme";
import { useIsMobile } from "../useMedia";
import { Check } from "../ui/icons";
import AppShell from "../ui/AppShell";
import Section from "../ui/Section";
import Card from "../ui/Card";
import Button from "../ui/Button";

const levelSkin = (lvl?: string | null) =>
  lvl === "높음" ? { fg: color.red, bg: color.redTint }
  : lvl === "보통" ? { fg: color.amber, bg: color.amberTint }
  : { fg: color.inkSoft, bg: color.bg };

function AccountCard({ user, onLogout }: { user: User; onLogout: () => void }) {
  const nav = useNavigate();
  const doLogout = async () => {
    try { await logout(); } finally { onLogout(); nav("/login"); }
  };
  return (
    <Card style={{ display: "flex", alignItems: "center", gap: 14 }}>
      <div style={{
        width: 42, height: 42, flexShrink: 0, borderRadius: 12,
        background: color.brandTint, color: color.brand,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: font.h2, fontWeight: 700,
      }}>
        {user.name.slice(0, 1) || "?"}
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
        <div style={{ fontSize: font.h2, fontWeight: 700 }}>{user.name}</div>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 5, alignSelf: "flex-start",
          background: color.greenTint, color: color.green,
          padding: "2px 9px", fontSize: font.caption, fontWeight: 600,
          borderRadius: 999,
        }}>
          <Check size={11} color={color.green} />
          {user.role === "senior" ? "어르신" : "보호자"} 계정
        </span>
      </div>
      <Button variant="ghost" onClick={doLogout}>로그아웃</Button>
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
      <h1 style={{ margin: 0, fontSize: font.h1, fontWeight: 700 }}>마이페이지</h1>
      <Section title="내 계정">
        <AccountCard user={user} onLogout={onLogout} />
      </Section>
    </AppShell>
  );
}

function GuardianHome({ user, onLogout }: { user: User; onLogout: () => void }) {
  const mobile = useIsMobile();
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
      <h1 style={{ margin: 0, fontSize: font.h1, fontWeight: 700 }}>마이페이지</h1>

      <Section title="내 계정">
        <AccountCard user={user} onLogout={onLogout} />
      </Section>

      <Section title="연결된 어르신" hint={`${linked.length}명`}>
        {linked.length === 0 && (
          <Card style={{ textAlign: "center", padding: "24px 18px" }}>
            <p style={{ margin: 0, fontSize: font.small, color: color.inkFaint }}>
              아직 연결된 어르신이 없습니다. 아래에서 코드로 연결하세요.
            </p>
          </Card>
        )}
        {linked.length > 0 && (
          <div style={{
            display: "grid", gap: 10,
            gridTemplateColumns: mobile ? "1fr" : "repeat(auto-fill, minmax(230px, 1fr))",
          }}>
            {linked.map((w) => {
              const s = levelSkin(w.risk_level);
              return (
                <Card key={w.id} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10,
                }}>
                  <div style={{ fontSize: font.body, fontWeight: 700 }}>{w.name}</div>
                  <span style={{
                    padding: "3px 10px", fontSize: font.caption, fontWeight: 700,
                    borderRadius: 999, color: s.fg, background: s.bg, whiteSpace: "nowrap",
                  }}>
                    {w.risk_level ? `위험도 ${w.risk_level}` : "자가진단 전"}
                  </span>
                </Card>
              );
            })}
          </div>
        )}
      </Section>

      <Section title="어르신 연결" hint="어르신 앱에서 발급한 6자리 코드">
        <Card style={{ display: "flex", gap: 10 }}>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="6자리 코드"
                 inputMode="numeric" maxLength={6}
                 style={{
                   flex: 1, padding: "9px 12px", fontSize: font.body,
                   border: `1px solid ${color.lineStrong}`, borderRadius: radius.md,
                   outline: "none",
                 }} />
          <Button onClick={join}>연결</Button>
        </Card>
        {error && (
          <p style={{ margin: 0, color: color.red, fontSize: font.small, fontWeight: 600 }}>
            {error}
          </p>
        )}
      </Section>
    </AppShell>
  );
}
