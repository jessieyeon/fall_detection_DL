import React, { useEffect, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { me } from "./api.js";
import Login from "./pages/Login.jsx";
import MyPage from "./pages/MyPage.jsx";
import Consulting from "./pages/Consulting.jsx";

export default function App() {
  const [user, setUser] = useState(undefined); // undefined=확인중, null=비로그인

  useEffect(() => {
    me().then(setUser).catch(() => setUser(null));
  }, []);

  if (user === undefined) return <p style={{ padding: 24 }}>불러오는 중…</p>;

  return (
    <Routes>
      <Route path="/login" element={<Login onLogin={setUser} />} />
      <Route
        path="/mypage"
        element={user ? <MyPage user={user} onLogout={() => setUser(null)} />
                       : <Navigate to="/login" replace />}
      />
      <Route
        path="/consulting"
        element={user ? <Consulting /> : <Navigate to="/login" replace />}
      />
      <Route path="*" element={<Navigate to={user ? "/mypage" : "/login"} replace />} />
    </Routes>
  );
}
