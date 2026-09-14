export type Role = "admin";
export interface User { id: number; email: string; role: Role; name: string; facility_name?: string }
export interface Facility { name: string; facility_name: string; address: string }
export interface Resident {
  id: number; name: string; age: number | null;
  room: string; phone: string; note: string;
  /** 개별 주소(선택). 비어 있으면 신고 지원이 시설 주소를 쓴다. */
  address: string;
  /** 상세 주소(동·호수 등). 우편번호 검색이 주지 못하는 부분이라 직접 입력받는다. */
  address_detail: string;
}
export interface Camera {
  id: number; name: string; location: string; device_key: string;
  paired_at: string; last_seen_at: string | null; online: boolean;
  resident_id: number | null; resident_name: string | null; resident_room: string | null;
}
/** 아직 등록되지 않은, 신호가 잡힌 기기. real=false 는 시연용 표본. */
export interface FoundDevice { device_key: string; label: string; real: boolean }
export interface Dispatch {
  id: number; camera_name: string; location: string;
  facility_name: string; address: string;
  resident_id: number | null; resident_name: string | null;
  age: number | null; room: string | null; phone: string | null;
  resident_address_detail?: string | null;
  dispatch_address: string; identified: boolean;
}
export interface Finding { zone: string; cell: [number, number]; score: number; level: string; recommendation: string }
export interface Report {
  id: number; summary: string; findings: Finding[]; location: string; created_at: string;
  /** 판정 기준의 문헌 근거 설명 (docs/낙상-동선-근거.md) */
  evidence?: string;
}
export interface ReportRow { id: number; user_id: number; created_at: string; location: string; summary: string }
export interface Hospital { name: string; address: string; phone: string; distance_m: number; url: string }

/** 쿠키가 저장되지 않는 환경(전시 iframe + 카카오톡 인앱 브라우저)을 위한 예비 인증.
 *
 *  그 환경에서는 로그인 응답의 Set-Cookie 가 저장되지 않는다. 로그인은 200 으로
 *  성공하고 화면도 넘어가는데 이후 요청이 전부 401 이라, 겉보기에는 로그인된 채
 *  아무것도 동작하지 않는 상태가 된다. localStorage 는 iframe 출처 기준으로
 *  동작해서 쿠키가 막혀도 살아남는다.
 *
 *  쿠키가 되는 환경에서는 서버가 쿠키를 먼저 보므로 이 토큰은 쓰이지 않는다. */
const TOKEN_KEY = "daon.token";

export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); }
  catch { /* 사파리 프라이빗 모드 등 저장이 막힌 환경 — 쿠키로만 간다 */ }
}

export function getToken(): string {
  try { return localStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; }
}

/** 토큰이 있으면 Authorization 헤더를 붙인다. */
function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function req<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    ...options,
    headers: { "Content-Type": "application/json", ...authHeaders(),
               ...(options.headers as Record<string, string> | undefined) },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error((detail as { detail?: string }).detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

// 인증
export const login = async (email: string, password: string) => {
  const u = await req<User & { token?: string }>(
    "/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  // 쿠키가 저장되지 않는 환경을 대비해 토큰을 보관한다. 쿠키가 되는 환경에서는
  // 서버가 쿠키를 먼저 보므로 그냥 들고만 있는 값이 된다.
  setToken(u.token ?? null);
  return u;
};
export const logout = async () => {
  try { return await req<{ status: string }>("/api/auth/logout", { method: "POST" }); }
  finally { setToken(null); }   // 서버 호출이 실패해도 토큰은 반드시 지운다
};
export const me = () => req<User>("/api/auth/me");

// 관리자 — 설치 공간 목록은 서버가 알려준다(프런트에 하드코딩하지 않는다)
export const adminMeta = () => req<{ locations: string[] }>("/api/admin/meta");

// 관리자 — 시설
export const getFacility = () => req<Facility>("/api/admin/facility");
export const setFacility = (body: { facility_name?: string; address?: string }) =>
  req<{ updated: boolean }>("/api/admin/facility", { method: "PATCH", body: JSON.stringify(body) });

// 관리자 — 입주민
export const listResidents = () => req<Resident[]>("/api/admin/residents");
export const createResident = (body: Partial<Resident> & { name: string }) =>
  req<{ id: number }>("/api/admin/residents", { method: "POST", body: JSON.stringify(body) });
export const updateResident = (id: number, body: Partial<Resident>) =>
  req<{ updated: boolean }>(`/api/admin/residents/${id}`, { method: "PATCH", body: JSON.stringify(body) });
export const deleteResident = (id: number) =>
  req<{ deleted: boolean }>(`/api/admin/residents/${id}`, { method: "DELETE" });

// 관리자 — 카메라
export const listCameras = () => req<Camera[]>("/api/admin/cameras");
export const scanCameras = () => req<FoundDevice[]>("/api/admin/cameras/scan");
export const registerCamera = (body: {
  device_key: string; name: string; location: string; resident_id?: number | null;
}) => req<{ id: number }>("/api/admin/cameras", { method: "POST", body: JSON.stringify(body) });
export const updateCamera = (id: number, body: {
  name?: string; location?: string; resident_id?: number | null; clear_resident?: boolean;
}) => req<{ updated: boolean }>(`/api/admin/cameras/${id}`, { method: "PATCH", body: JSON.stringify(body) });
export const deleteCamera = (id: number) =>
  req<{ deleted: boolean }>(`/api/admin/cameras/${id}`, { method: "DELETE" });
export const dispatchInfo = (cameraId: number) =>
  req<Dispatch>(`/api/admin/cameras/${cameraId}/dispatch`);

// 근처 병원 — 신고 지원 화면에서 함께 보여준다
export const hospitals = (coords?: { lat: number; lng: number }) =>
  req<Hospital[]>(`/api/home/hospitals${coords ? `?lat=${coords.lat}&lng=${coords.lng}` : ""}`);

// 컨설팅
export const analyzeVideo = (file: File, location = "") => {
  const form = new FormData();
  form.append("file", file);
  form.append("location", location);
  return fetch("/api/consulting/analyze", { method: "POST", credentials: "include",
                                           headers: authHeaders(), body: form })
    .then((r) => { if (!r.ok) throw new Error("업로드 실패"); return r.json() as Promise<{ job_id: string }>; });
};
export const consultingStatus = (jobId: string) =>
  req<{ status: "pending" | "done" | "error"; report_id: number | null; error: string | null }>(`/api/consulting/status/${jobId}`);
export const consultingReports = () => req<ReportRow[]>("/api/consulting/reports");
export const consultingReport = (rid: number) => req<Report>(`/api/consulting/report/${rid}`);
export const consultingImageUrl = (rid: number) => `/api/consulting/report/${rid}/image`;

/** 동선 이미지를 blob URL 로 가져온다.
 *
 *  `<img src>` 로 직접 불러오면 Authorization 헤더를 붙일 수 없다. 쿠키가 막힌
 *  환경(전시 iframe + 인앱 브라우저)에서는 그 요청만 401 이 되어 이미지가
 *  깨진 채로 뜬다 — 분석은 성공했는데 그림만 물음표가 되는 증상이었다.
 *
 *  토큰을 쿼리스트링에 넣는 방법도 있지만, 그러면 서버 로그·리퍼러에 토큰이
 *  남는다. fetch 로 받아 blob 으로 바꾸는 편이 안전하다.
 *
 *  호출자는 다 쓴 뒤 URL.revokeObjectURL 로 해제해야 한다. */
export async function fetchConsultingImage(rid: number): Promise<string> {
  const res = await fetch(consultingImageUrl(rid), {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`이미지를 불러오지 못했습니다 (${res.status})`);
  return URL.createObjectURL(await res.blob());
}
