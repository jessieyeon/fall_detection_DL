import React from "react";
import { useNavigate } from "react-router-dom";
import { logout } from "../api.js";

export default function MyPage({ user, onLogout }) {
  const nav = useNavigate();

  async function doLogout() {
    await logout();
    onLogout();
    nav("/login");
  }

  return (
    <div style={{ padding: 24 }}>
      <h1>마이페이지</h1>
      <p>{user.name}님 ({user.role === "senior" ? "어르신" : "보호자"})</p>
      <button onClick={doLogout}>로그아웃</button>
      {/* P2에서 설문·보호자매칭·평면도·병원 섹션이 여기에 붙는다 */}
    </div>
  );
}
