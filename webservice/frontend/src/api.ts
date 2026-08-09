export type Role = "admin";
export interface User { id: number; email: string; role: Role; name: string; facility_name?: string }
export interface Facility { name: string; facility_name: string; address: string }
export interface Resident {
  id: number; name: string; age: number | null;
  room: string; phone: string; note: string;
  /** 개별 주소(선택). 비어 있으면 신고 지원이 시설 주소를 쓴다. */
  address: string;
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

async function req<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error((detail as { detail?: string }).detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

// 인증
export const login = (email: string, password: string) =>
  req<User>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const logout = () => req<{ status: string }>("/api/auth/logout", { method: "POST" });
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
  return fetch("/api/consulting/analyze", { method: "POST", credentials: "include", body: form })
    .then((r) => { if (!r.ok) throw new Error("업로드 실패"); return r.json() as Promise<{ job_id: string }>; });
};
export const consultingStatus = (jobId: string) =>
  req<{ status: "pending" | "done" | "error"; report_id: number | null; error: string | null }>(`/api/consulting/status/${jobId}`);
export const consultingReports = () => req<ReportRow[]>("/api/consulting/reports");
export const consultingReport = (rid: number) => req<Report>(`/api/consulting/report/${rid}`);
export const consultingImageUrl = (rid: number) => `/api/consulting/report/${rid}/image`;
