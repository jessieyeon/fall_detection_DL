import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  logout, surveyQuestions, submitSurvey, latestSurvey, makeCode, redeemCode,
  guardianList, wards, hospitals, floorplanUrl,
  type User, type SurveyLatest, type Question, type Person, type Ward, type Hospital,
} from "../api";
import { color, edge } from "../theme";
import { Check, Person as PersonIcon, Phone, MapPin, Gear } from "../ui/icons";
import AppShell from "../ui/AppShell";
import Section from "../ui/Section";
import Card from "../ui/Card";
import Button from "../ui/Button";

const fmtDist = (m: number) => (m < 1000 ? `${m}m` : `${(m / 1000).toFixed(1)}km`);
const daysAgo = (iso: string) => Math.max(0, Math.floor((Date.now() - Date.parse(iso.replace(" ", "T"))) / 86400000));
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
      <Button variant="outline" onClick={doLogout}>LOGOUT</Button>
    </Card>
  );
}

export default function MyPage({ user, onLogout }: { user: User; onLogout: () => void }) {
  return user.role === "guardian"
    ? <GuardianHome user={user} onLogout={onLogout} />
    : <SeniorHome user={user} onLogout={onLogout} />;
}

function SeniorHome({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [latest, setLatest] = useState<SurveyLatest | null>(null);
  const [questions, setQuestions] = useState<Question[] | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [guardians, setGuardians] = useState<Person[]>([]);
  const [code, setCode] = useState("");
  const [hosp, setHosp] = useState<Hospital[]>([]);
  const [hospErr, setHospErr] = useState("");

  const loadHospitals = () => hospitals().then((h) => { setHosp(h); setHospErr(""); }).catch((e) => setHospErr((e as Error).message));

  useEffect(() => {
    latestSurvey().then(setLatest).catch(() => {});
    guardianList().then(setGuardians).catch(() => {});
    loadHospitals();
  }, []);

  async function startSurvey() {
    const q = await surveyQuestions();
    setQuestions(q.questions);
    setAnswers(Object.fromEntries(q.questions.map((x) => [x.id, 0])));
  }
  async function submit() {
    const res = await submitSurvey(answers);
    setLatest({ score: res.score, risk_level: res.risk_level, created_at: new Date().toISOString() });
    setQuestions(null);
  }

  return (
    <AppShell active="mypage" right={<Gear size={20} />}>
      <Section title="My Account" divider={false}>
        <AccountCard user={user} onLogout={onLogout} />
      </Section>

      <Section title="Safety Assessment">
        {questions ? (
          <Card style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {questions.map((q) => (
              <div key={q.id} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ fontWeight: 700 }}>{q.text}</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                  {q.options.map((o, i) => (
                    <label key={i} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <input type="radio" name={q.id} checked={answers[q.id] === i}
                             onChange={() => setAnswers({ ...answers, [q.id]: i })} />
                      {o.label}
                    </label>
                  ))}
                </div>
              </div>
            ))}
            <Button big full onClick={submit}>제출</Button>
          </Card>
        ) : (
          <Card style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <p style={{ margin: 0, fontSize: 20, lineHeight: 1.5 }}>
              {latest
                ? `최근 진단: ${latest.risk_level} (점수 ${latest.score}) · ${daysAgo(latest.created_at)}일 전. 매달 갱신을 권장합니다.`
                : "아직 자가진단을 하지 않았습니다. 지금 시작해 안전 상태를 점검하세요."}
            </p>
            <Button big full onClick={startSurvey}>START SURVEY</Button>
          </Card>
        )}
      </Section>

      <Section title="Emergency Contact">
        {guardians.map((g) => (
          <Card key={g.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{ width: 42, height: 56, background: color.blue2, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center", ...edge(2) }}>
                <PersonIcon size={24} />
              </div>
              <div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>{g.name}</div>
                <div style={{ color: color.gray, fontSize: 16 }}>보호자</div>
              </div>
            </div>
            <Button variant="outline" icon={<Phone size={18} />}>CALL</Button>
          </Card>
        ))}
        <Card style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <span style={{ color: color.gray }}>{code ? <>연결 코드: <b style={{ color: color.ink, fontSize: 20 }}>{code}</b></> : "보호자에게 줄 6자리 코드를 만드세요."}</span>
          <Button variant="outline" onClick={async () => setCode((await makeCode()).code)}>코드 생성</Button>
        </Card>
      </Section>

      <Section title="My Home Map">
        <Card pad={0} style={{ overflow: "hidden" }}>
          <div style={{ position: "relative", background: color.blue3, minHeight: 120 }}>
            {user.apartment_name
              ? <img src={floorplanUrl(user.apartment_name)} alt="평면도" style={{ display: "block", width: "100%" }}
                     onError={(e) => { (e.currentTarget.style.display = "none"); }} />
              : <p style={{ margin: 0, padding: 24, color: color.gray }}>등록된 아파트 평면도가 없습니다.</p>}
            {user.apartment_name && (
              <a href={floorplanUrl(user.apartment_name)} target="_blank" rel="noreferrer"
                 style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", textDecoration: "none" }}>
                <Button icon={<MapPin size={18} color="white" />}>VIEW FULL LAYOUT</Button>
              </a>
            )}
          </div>
          <div style={{ padding: 16, borderTop: `2px solid ${color.black}`, fontSize: 18 }}>
            거주지: {user.apartment_name || "미등록"}
          </div>
        </Card>
      </Section>

      <Section title="Emergency Care Nearby" titleColor={color.red}>
        {hospErr && (
          <Card style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <span style={{ color: color.gray }}>병원 정보를 불러오지 못했습니다. (카카오 키 확인)</span>
            <Button variant="outline" onClick={loadHospitals}>다시</Button>
          </Card>
        )}
        {hosp.slice(0, 5).map((h, i) => (
          <Card key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{h.name}</div>
              <div style={{ color: color.gray, fontSize: 16 }}>{fmtDist(h.distance_m)} 거리</div>
            </div>
            <Button as="a" href={h.phone ? `tel:${h.phone}` : undefined} variant="outline"
                    style={{ textDecoration: "none", padding: 16 }}>
              <Phone size={24} color={color.red} />
            </Button>
          </Card>
        ))}
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
    <AppShell active="mypage" right={<Gear size={20} />}>
      <Section title="My Account" divider={false}>
        <AccountCard user={user} onLogout={onLogout} />
      </Section>

      <Section title="Monitored Seniors">
        {linked.length === 0 && <p style={{ margin: 0, color: color.gray }}>아직 연결된 어르신이 없습니다. 아래에서 코드로 연결하세요.</p>}
        {linked.map((w) => (
          <Card key={w.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{w.name}</div>
            <span style={{ padding: "4px 12px", fontWeight: 700, color: color.white, background: levelColor(w.risk_level) }}>
              {w.risk_level ? `위험 ${w.risk_level}` : "자가진단 미실시"}
            </span>
          </Card>
        ))}
      </Section>

      <Section title="Connect a Senior">
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
