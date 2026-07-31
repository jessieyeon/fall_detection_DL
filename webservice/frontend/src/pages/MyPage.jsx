import React from "react";
import { useNavigate } from "react-router-dom";
import { logout } from "../api.js";
import SurveySection from "../sections/SurveySection.jsx";
import GuardianSection from "../sections/GuardianSection.jsx";
import HomeSection from "../sections/HomeSection.jsx";

export default function MyPage({ user, onLogout }) {
  const nav = useNavigate();

  async function doLogout() {
    try { await logout(); } finally { onLogout(); nav("/login"); }
  }

  return (
    <div style={{ padding: 24, maxWidth: 640 }}>
      <h1>마이페이지</h1>
      <p>{user.name}님 ({user.role === "senior" ? "어르신" : "보호자"})</p>
      <button onClick={doLogout}>로그아웃</button>

      {user.role === "senior" && <SurveySection />}
      <GuardianSection role={user.role} />
      {user.role === "senior" && <HomeSection apartment={user.apartment_name} />}
    </div>
  );
}
