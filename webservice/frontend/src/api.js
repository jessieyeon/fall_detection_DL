async function req(path, options = {}) {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
  return res.json();
}

export const login = (email, password) =>
  req("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const logout = () => req("/api/auth/logout", { method: "POST" });
export const me = () => req("/api/auth/me");

// 설문
export const surveyQuestions = () => req("/api/survey/questions");
export const submitSurvey = (answers) =>
  req("/api/survey", { method: "POST", body: JSON.stringify({ answers }) });
export const latestSurvey = () => req("/api/survey/latest");

// 보호자 매칭
export const makeCode = () => req("/api/guardian/code", { method: "POST" });
export const redeemCode = (code) =>
  req("/api/guardian/redeem", { method: "POST", body: JSON.stringify({ code }) });
export const wards = () => req("/api/guardian/wards");
export const guardianList = () => req("/api/guardian/list");

// 홈
export const hospitals = () => req("/api/home/hospitals");
export const floorplanUrl = (apartment) =>
  `/api/home/floorplan?apartment=${encodeURIComponent(apartment)}`;

// 컨설팅
export const analyzeVideo = (file) => {
  const form = new FormData();
  form.append("file", file);
  return fetch("/api/consulting/analyze", {
    method: "POST", credentials: "include", body: form,
  }).then((r) => { if (!r.ok) throw new Error("업로드 실패"); return r.json(); });
};
export const consultingStatus = (jobId) => req(`/api/consulting/status/${jobId}`);
export const consultingReports = () => req("/api/consulting/reports");
export const consultingReport = (rid) => req(`/api/consulting/report/${rid}`);
export const consultingImageUrl = (rid) => `/api/consulting/report/${rid}/image`;
