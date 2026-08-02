export type Role = "senior" | "guardian";
export interface User { id: number; email: string; role: Role; name: string; apartment_name?: string }
export interface SurveyLatest { score: number; risk_level: string; created_at: string }
export interface Question { id: string; text: string; options: { label: string; points: number }[] }
export interface Questionnaire { questions: Question[]; thresholds: Record<string, number> }
export interface Finding { zone: string; cell: [number, number]; score: number; level: string; recommendation: string }
export interface Report { id: number; summary: string; findings: Finding[]; location: string; created_at: string }
export interface ReportRow { id: number; user_id: number; created_at: string; location: string; summary: string }
export interface Hospital { name: string; address: string; phone: string; distance_m: number; url: string }
export interface Ward { id: number; name: string; risk_level: string | null }
export interface Person { id: number; name: string }

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

// 설문
export const surveyQuestions = () => req<Questionnaire>("/api/survey/questions");
export const submitSurvey = (answers: Record<string, number>) =>
  req<{ score: number; risk_level: string }>("/api/survey", { method: "POST", body: JSON.stringify({ answers }) });
export const latestSurvey = () => req<SurveyLatest | null>("/api/survey/latest");

// 보호자 매칭
export const makeCode = () => req<{ code: string }>("/api/guardian/code", { method: "POST" });
export const redeemCode = (code: string) =>
  req<{ senior: Person }>("/api/guardian/redeem", { method: "POST", body: JSON.stringify({ code }) });
export const wards = () => req<Ward[]>("/api/guardian/wards");
export const guardianList = () => req<Person[]>("/api/guardian/list");

// 홈
export const hospitals = (coords?: { lat: number; lng: number }) =>
  req<Hospital[]>(`/api/home/hospitals${coords ? `?lat=${coords.lat}&lng=${coords.lng}` : ""}`);
export const floorplanUrl = (apartment: string) =>
  `/api/home/floorplan?apartment=${encodeURIComponent(apartment)}`;

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
