import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  adminMeta, createResident, deleteCamera, deleteResident,
  listCameras, listResidents, logout, registerCamera, scanCameras,
  updateCamera, updateResident,
  type Camera, type FoundDevice, type Resident, type User,
} from "../api";
import { color, font, radius } from "../theme";
import { useIsMobile } from "../useMedia";
import { Check, Video, Person, Wifi, MapPin } from "../ui/icons";
import AppShell from "../ui/AppShell";
import Section from "../ui/Section";
import Card from "../ui/Card";
import Button from "../ui/Button";

/** 탐색 애니메이션 길이. 실제 조회는 즉시 끝나지만, 결과가 번쩍 나타나면
 *  '찾은' 것이 아니라 '원래 있던' 목록처럼 보인다. */
const SCAN_MS = 1800;

const inputStyle = {
  width: "100%", padding: "9px 12px", fontSize: font.body,
  border: `1px solid ${color.lineStrong}`, borderRadius: radius.md,
  outline: "none", boxSizing: "border-box" as const,
};

function Field({ label, ...rest }: { label: string } & Record<string, unknown>) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 5, flex: 1, minWidth: 0 }}>
      <span style={{ fontSize: font.caption, color: color.inkFaint, fontWeight: 600 }}>
        {label}
      </span>
      <input style={inputStyle} {...rest} />
    </label>
  );
}

// ── 연락처 ────────────────────────────────────────────────────────────

/** 연락처 자릿수. 3-4-4 로 고정한다(010-1234-5678). */
const PHONE_DIGITS = 11;

/**
 * 입력 중인 값을 010-1234-5678 모양으로 만든다.
 *
 * 사용자가 친 것에서 숫자만 뽑아 다시 조립한다. 하이픈을 '끼워 넣는' 방식이
 * 아니라 매번 새로 만드는 방식인 이유: 붙여넣기(01012345678, 010 1234 5678,
 * +82-10-… 을 지운 뒤 등)와 중간 지우기가 전부 같은 경로로 처리돼서, 어떤
 * 순서로 편집해도 결과가 한 가지 모양으로 수렴한다.
 *
 * 11자리를 넘는 입력은 잘라낸다 — 실수로 한 번 더 누른 숫자가 조용히 들어가
 * 119 에 잘못된 번호를 읽어주는 것보다, 아예 안 들어가는 편이 낫다.
 */
export function formatPhone(raw: string): string {
  const d = (raw || "").replace(/\D/g, "").slice(0, PHONE_DIGITS);
  if (d.length <= 3) return d;
  if (d.length <= 7) return `${d.slice(0, 3)}-${d.slice(3)}`;
  return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`;
}

/** 저장해도 되는 값인지. 비어 있는 것은 허용한다(연락처는 선택 항목). */
function phoneComplete(value: string): boolean {
  const d = (value || "").replace(/\D/g, "");
  return d.length === 0 || d.length === PHONE_DIGITS;
}

function ErrorText({ children }: { children?: string }) {
  if (!children) return null;
  return (
    <p style={{ margin: 0, color: color.red, fontSize: font.small, fontWeight: 600 }}>
      {children}
    </p>
  );
}

// ── 계정 ──────────────────────────────────────────────────────────────

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
          관리자 계정
        </span>
      </div>
      <Button variant="ghost" onClick={doLogout}>로그아웃</Button>
    </Card>
  );
}

// ── 주소 ──────────────────────────────────────────────────────────────

const POSTCODE_SRC =
  "https://t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js";

type PostcodeData = { roadAddress: string; jibunAddress: string; buildingName: string };
declare global {
  interface Window {
    daum?: { Postcode: new (o: { oncomplete: (d: PostcodeData) => void }) => { open: () => void } };
  }
}

/** 카카오(다음) 우편번호 스크립트를 필요할 때 한 번만 불러온다.
 *  앱 첫 로딩에 끼워 넣으면 주소를 안 건드리는 관람객까지 비용을 낸다. */
function loadPostcode(): Promise<void> {
  if (window.daum?.Postcode) return Promise.resolve();
  const existing = document.querySelector<HTMLScriptElement>(`script[src="${POSTCODE_SRC}"]`);
  if (existing) {
    return new Promise((res, rej) => {
      existing.addEventListener("load", () => res());
      existing.addEventListener("error", () => rej(new Error("주소 검색을 불러오지 못했습니다")));
    });
  }
  return new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = POSTCODE_SRC;
    s.onload = () => res();
    s.onerror = () => rej(new Error("주소 검색을 불러오지 못했습니다"));
    document.head.appendChild(s);
  });
}

// ── 나의 카메라 ───────────────────────────────────────────────────────

function StatusDot({ online }: { online: boolean }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "3px 10px", borderRadius: 999, whiteSpace: "nowrap",
      fontSize: font.caption, fontWeight: 700,
      color: online ? color.green : color.inkFaint,
      background: online ? color.greenTint : color.bg,
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: 999,
        background: online ? color.green : color.lineStrong,
      }} />
      {online ? "연결됨" : "대기 중"}
    </span>
  );
}

function CameraSection({ residents }: { residents: Resident[] }) {
  const mobile = useIsMobile();
  const [cams, setCams] = useState<Camera[]>([]);
  const [locations, setLocations] = useState<string[]>([]);
  const [scanning, setScanning] = useState(false);
  const [found, setFound] = useState<FoundDevice[] | null>(null);
  const [picked, setPicked] = useState<FoundDevice | null>(null);
  const [form, setForm] = useState({ name: "", location: "", resident_id: "" });
  const [error, setError] = useState("");

  const load = () => listCameras().then(setCams).catch(() => {});
  useEffect(() => {
    load();
    adminMeta().then((m) => {
      setLocations(m.locations);
      setForm((f) => ({ ...f, location: m.locations[0] ?? "" }));
    }).catch(() => {});
    // 연결 상태는 파이프라인이 살아 있는 동안만 참이라 주기적으로 다시 본다.
    const t = setInterval(load, 10_000);
    return () => clearInterval(t);
  }, []);

  const scan = async () => {
    setError(""); setPicked(null); setFound(null); setScanning(true);
    try {
      const [devices] = await Promise.all([
        scanCameras(),
        new Promise((r) => setTimeout(r, SCAN_MS)),
      ]);
      setFound(devices);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setScanning(false);
    }
  };

  const register = async () => {
    if (!picked) return;
    setError("");
    try {
      await registerCamera({
        device_key: picked.device_key,
        name: form.name.trim() || picked.label,
        location: form.location,
        resident_id: form.resident_id ? Number(form.resident_id) : null,
      });
      setPicked(null); setFound(null);
      setForm({ name: "", location: locations[0] ?? "", resident_id: "" });
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const unlink = async (cam: Camera) => {
    await deleteCamera(cam.id);
    load();
  };

  const reassign = async (cam: Camera, value: string) => {
    await updateCamera(cam.id, value
      ? { resident_id: Number(value) }
      : { clear_resident: true });
    load();
  };

  return (
    <Section title="나의 카메라" hint={`${cams.length}대 · 연결됨 ${cams.filter((c) => c.online).length}대`}>
      {cams.length === 0 && (
        <Card style={{ textAlign: "center", padding: "24px 18px" }}>
          <p style={{ margin: 0, fontSize: font.small, color: color.inkFaint }}>
            등록된 카메라가 없습니다. 아래에서 주변 카메라를 찾아 연결하세요.
          </p>
        </Card>
      )}

      {cams.length > 0 && (
        <div style={{
          display: "grid", gap: 10,
          gridTemplateColumns: mobile ? "1fr" : "repeat(auto-fill, minmax(300px, 1fr))",
        }}>
          {cams.map((cam) => (
            <Card key={cam.id} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                <Video size={17} color={color.brand} />
                <span style={{ fontSize: font.body, fontWeight: 700, flex: 1, minWidth: 0 }}>
                  {cam.name}
                </span>
                <StatusDot online={cam.online} />
              </div>

              <div style={{
                display: "flex", alignItems: "center", gap: 6,
                fontSize: font.caption, color: color.inkFaint,
              }}>
                <MapPin size={12} color={color.inkFaint} />
                {cam.location}
                <span style={{ marginLeft: "auto", fontFamily: "monospace" }}>
                  {cam.device_key}
                </span>
              </div>

              <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                <span style={{ fontSize: font.caption, color: color.inkFaint, fontWeight: 600 }}>
                  연결된 어르신
                </span>
                <select value={cam.resident_id ?? ""} style={inputStyle}
                        onChange={(e) => reassign(cam, e.target.value)}>
                  <option value="">지정 안 함 (공용공간)</option>
                  {residents.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}{r.room ? ` · ${r.room}` : ""}
                    </option>
                  ))}
                </select>
              </label>

              <Button variant="ghost" style={{ alignSelf: "flex-start", color: color.red }}
                      onClick={() => unlink(cam)}>
                연결 해제
              </Button>
            </Card>
          ))}
        </div>
      )}

      {/* 기기 탐색 — 버튼은 '어르신 추가'와 같은 모양(outline·좌측 정렬)으로
          둔다. 두 섹션이 하는 일이 같은데(목록에 하나 더한다) 버튼만 달라
          보이면 한쪽이 더 중요한 동작처럼 읽힌다. 눌러야 탐색 카드가 열리는
          흐름도 '어르신 추가' 쪽과 맞췄다. */}
      {!scanning && found === null && (
        <Button variant="outline" style={{ alignSelf: "flex-start" }} onClick={scan}>
          카메라 추가
        </Button>
      )}

      {(scanning || found !== null) && (
      <Card style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
        }}>
          <Wifi size={15} color={color.brand} />
          <span style={{ fontSize: font.caption, color: color.inkFaint }}>
            같은 네트워크에 켜져 있는 카메라를 찾습니다
          </span>
          <button onClick={() => { setFound(null); setPicked(null); setError(""); }}
                  style={{ marginLeft: "auto", fontSize: font.caption, color: color.inkFaint }}>
            닫기
          </button>
        </div>

        {scanning && (
          <div style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "14px 4px", fontSize: font.small, color: color.inkSoft,
          }}>
            <span style={{
              width: 14, height: 14, borderRadius: 999, flexShrink: 0,
              border: `2px solid ${color.brandTint2}`, borderTopColor: color.brand,
              animation: "daon-spin .8s linear infinite",
            }} />
            주변 카메라를 찾는 중…
          </div>
        )}

        {found && found.length === 0 && !scanning && (
          <p style={{ margin: 0, fontSize: font.small, color: color.inkFaint }}>
            새로 발견된 카메라가 없습니다. 카메라 전원과 네트워크를 확인해 주세요.
          </p>
        )}

        {found && found.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {found.map((d) => {
              const on = picked?.device_key === d.device_key;
              return (
                <button key={d.device_key} onClick={() => {
                  setPicked(d);
                  setForm((f) => ({ ...f, name: d.real ? "" : d.label }));
                }} style={{
                  display: "flex", alignItems: "center", gap: 10, textAlign: "left",
                  padding: "10px 12px", cursor: "pointer",
                  borderRadius: radius.md,
                  border: `1px solid ${on ? color.brand : color.line}`,
                  background: on ? color.brandTint : color.surface,
                }}>
                  <Video size={16} color={on ? color.brand : color.inkFaint} />
                  <span style={{ flex: 1, minWidth: 0, fontSize: font.body, fontWeight: 600 }}>
                    {d.label}
                  </span>
                  <span style={{ fontSize: font.caption, color: color.inkFaint,
                                 fontFamily: "monospace" }}>
                    {d.device_key}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {picked && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Field label="카메라 이름" placeholder="예) 3층 복도" value={form.name}
                     onChange={(e: { target: { value: string } }) =>
                       setForm({ ...form, name: e.target.value })} />
              <label style={{ display: "flex", flexDirection: "column", gap: 5, flex: 1, minWidth: 0 }}>
                <span style={{ fontSize: font.caption, color: color.inkFaint, fontWeight: 600 }}>
                  설치 공간
                </span>
                <select value={form.location} style={inputStyle}
                        onChange={(e) => setForm({ ...form, location: e.target.value })}>
                  {locations.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 5, flex: 1, minWidth: 0 }}>
                <span style={{ fontSize: font.caption, color: color.inkFaint, fontWeight: 600 }}>
                  연결할 어르신 (선택)
                </span>
                <select value={form.resident_id} style={inputStyle}
                        onChange={(e) => setForm({ ...form, resident_id: e.target.value })}>
                  <option value="">지정 안 함 (공용공간)</option>
                  {residents.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}{r.room ? ` · ${r.room}` : ""}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <Button onClick={register} style={{ alignSelf: "flex-start" }}>연결</Button>
          </div>
        )}

        <ErrorText>{error}</ErrorText>
      </Card>
      )}

      {/* 탐색 카드가 닫힌 상태에서 난 오류(주로 탐색 요청 자체의 실패) */}
      {!scanning && found === null && <ErrorText>{error}</ErrorText>}
    </Section>
  );
}

// ── 어르신 정보 ───────────────────────────────────────────────────────

function ResidentSection({ residents, reload }:
                         { residents: Resident[]; reload: () => void }) {
  const mobile = useIsMobile();
  const empty = {
    name: "", age: "", room: "", phone: "", note: "",
    address: "", address_detail: "",
  };
  const [form, setForm] = useState(empty);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  // 수정 중인 어르신 id. null 이면 새로 추가하는 중이다. 추가 폼과 수정 폼이
  // 필드가 똑같아서 하나를 돌려 쓴다 — 두 벌로 두면 항목을 늘릴 때마다
  // 한쪽만 고치는 실수가 난다.
  const [editing, setEditing] = useState<number | null>(null);

  const close = () => { setOpen(false); setEditing(null); setForm(empty); setError(""); };

  const startEdit = (r: Resident) => {
    setError("");
    setEditing(r.id);
    setForm({
      name: r.name,
      age: r.age == null ? "" : String(r.age),
      room: r.room ?? "",
      // 형식이 생기기 전에 저장된 번호도 수정 화면에서는 3-4-4 로 보여준다
      phone: formatPhone(r.phone ?? ""),
      note: r.note ?? "", address: r.address ?? "",
      address_detail: r.address_detail ?? "",
    });
    setOpen(true);
  };

  const save = async () => {
    setError("");
    // 반쯤 적힌 번호는 저장하지 않는다. 119 에 읽어줄 번호라, 비어 있는 것보다
    // '있는데 틀린' 쪽이 훨씬 나쁘다.
    if (!phoneComplete(form.phone)) {
      setError("연락처는 010-1234-5678 형식으로 11자리를 입력해 주세요.");
      return;
    }
    const body = {
      name: form.name,
      age: form.age ? Number(form.age) : null,
      room: form.room, phone: form.phone, note: form.note,
      address: form.address, address_detail: form.address_detail,
    };
    try {
      if (editing == null) await createResident(body);
      // 서버는 null 필드를 무시하므로(exclude_none) 나이를 지우려면 값을
      // 빼는 게 아니라 아예 보내지 않는 편이 안전하다.
      else await updateResident(editing, form.age
        ? body
        : { ...body, age: undefined });
      close();
      reload();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  // 시설 주소와 같은 카카오 우편번호 검색을 쓴다. 직접 타이핑한 주소는
  // 오타·비표준 표기가 섞여 119 지원 화면에서 그대로 읽기 어렵다.
  const searchAddress = async () => {
    setError("");
    try {
      await loadPostcode();
      new window.daum!.Postcode({
        oncomplete: (d) => setForm((prev) =>
          ({ ...prev, address: d.roadAddress || d.jibunAddress })),
      }).open();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const remove = async (r: Resident) => {
    await deleteResident(r.id);
    reload();
  };

  return (
    <Section title="어르신 정보" hint={`${residents.length}명`}>
      <p style={{ margin: 0, fontSize: font.small, color: color.inkSoft }}>
        낙상이 감지되면 이 정보로 119 신고를 지원합니다.
      </p>

      {residents.length > 0 && (
        <div style={{
          display: "grid", gap: 10,
          gridTemplateColumns: mobile ? "1fr" : "repeat(auto-fill, minmax(260px, 1fr))",
        }}>
          {residents.map((r) => (
            <Card key={r.id} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Person size={16} color={color.brand} />
                <span style={{ fontSize: font.body, fontWeight: 700 }}>{r.name}</span>
                {r.age != null && (
                  <span style={{ fontSize: font.caption, color: color.inkFaint }}>
                    {r.age}세
                  </span>
                )}
                <span style={{ marginLeft: "auto", fontSize: font.caption,
                               color: color.inkSoft, fontWeight: 600 }}>
                  {r.room}
                </span>
              </div>
              {r.phone && (
                <div style={{ fontSize: font.caption, color: color.inkFaint }}>{r.phone}</div>
              )}
              {r.note && (
                <div style={{ fontSize: font.caption, color: color.inkSoft }}>{r.note}</div>
              )}
              {r.address && (
                <div style={{ fontSize: font.caption, color: color.inkFaint }}>
                  {[r.address, r.address_detail].filter(Boolean).join(" ")}
                </div>
              )}
              <div style={{ display: "flex", gap: 4, marginTop: "auto" }}>
                <Button variant="ghost" onClick={() => startEdit(r)}>수정</Button>
                <Button variant="ghost" style={{ color: color.red }}
                        onClick={() => remove(r)}>
                  삭제
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {!open && (
        <Button variant="outline" style={{ alignSelf: "flex-start" }}
                onClick={() => { setEditing(null); setForm(empty); setOpen(true); }}>
          어르신 추가
        </Button>
      )}

      {open && (
        <Card style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ fontSize: font.small, fontWeight: 700 }}>
            {editing == null ? "어르신 추가" : `${form.name || "어르신"} 정보 수정`}
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Field label="이름" value={form.name}
                   onChange={(e: { target: { value: string } }) =>
                     setForm({ ...form, name: e.target.value })} />
            <Field label="나이" value={form.age} inputMode="numeric"
                   onChange={(e: { target: { value: string } }) =>
                     setForm({ ...form, age: e.target.value })} />
            <Field label="호실" placeholder="예) 302호" value={form.room}
                   onChange={(e: { target: { value: string } }) =>
                     setForm({ ...form, room: e.target.value })} />
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {/* 하이픈은 타이핑하는 대로 자동으로 들어간다. inputMode=numeric 은
                모바일에서 숫자 자판이 바로 뜨게 한다 — 어르신 정보를 넣는 분이
                현장에서 폰으로 입력하는 경우가 많다. */}
            <Field label="연락처" value={form.phone} inputMode="numeric"
                   placeholder="010-1234-5678" maxLength={13}
                   onChange={(e: { target: { value: string } }) =>
                     setForm({ ...form, phone: formatPhone(e.target.value) })} />
            <Field label="비고" placeholder="예) 보행 보조기 사용" value={form.note}
                   onChange={(e: { target: { value: string } }) =>
                     setForm({ ...form, note: e.target.value })} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            <span style={{ fontSize: font.caption, color: color.inkFaint, fontWeight: 600 }}>
              주소 <span style={{ fontWeight: 400 }}>
                (선택 — 시설 밖에 거주하시면 입력, 비우면 시설 주소로 신고 지원)
              </span>
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <input readOnly value={form.address} placeholder="주소 검색을 눌러 주세요"
                     onClick={searchAddress}
                     style={{ ...inputStyle, cursor: "pointer", background: color.bg }} />
              <Button variant="outline" onClick={searchAddress}
                      icon={<MapPin size={14} color={color.brand} />}
                      style={{ flexShrink: 0 }}>
                주소 검색
              </Button>
            </div>
            {/* 상세 주소는 따로 받는다. 우편번호 검색은 도로명까지만 주므로
                동·호수·층은 여기서 채워야 119 에 읽어줄 주소가 완성된다.
                주소를 아직 안 고른 상태에서 상세만 적어두면 신고 화면에
                동떨어진 조각만 남으므로, 주소가 있을 때만 연다. */}
            {form.address && (
              <input value={form.address_detail}
                     placeholder="상세 주소 (예: 101동 1203호)"
                     onChange={(e) =>
                       setForm({ ...form, address_detail: e.target.value })}
                     style={inputStyle} />
            )}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button onClick={save}>{editing == null ? "추가" : "저장"}</Button>
            <Button variant="ghost" onClick={close}>취소</Button>
          </div>
          <ErrorText>{error}</ErrorText>
        </Card>
      )}
    </Section>
  );
}

// ── 페이지 ────────────────────────────────────────────────────────────

export default function MyPage({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [residents, setResidents] = useState<Resident[]>([]);
  const reload = () => listResidents().then(setResidents).catch(() => {});
  useEffect(() => { reload(); }, []);

  return (
    <AppShell active="mypage">
      <style>{"@keyframes daon-spin{to{transform:rotate(360deg)}}"}</style>
      <h1 style={{ margin: 0, fontSize: font.h1, fontWeight: 700 }}>마이페이지</h1>

      <Section title="내 계정">
        <AccountCard user={user} onLogout={onLogout} />
      </Section>

      {/* 시설 주소 입력 카드는 뺐다. 주소는 어르신마다 다를 수 있어(시설 밖
          거주 등) '어르신 정보'의 개별 주소로 일원화했다. 시설 주소를 쓰던
          119 지원은 개별 주소가 비었을 때만 시설 값을 쓰도록 남아 있다. */}
      <CameraSection residents={residents} />

      <ResidentSection residents={residents} reload={reload} />
    </AppShell>
  );
}
