import { useEffect, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { me, type User } from "./api";
import { color } from "./theme";
import Login from "./pages/Login";
import MyPage from "./pages/MyPage";
import Consulting from "./pages/Consulting";
import Live from "./pages/Live";

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined); // undefined=확인중

  useEffect(() => {
    me().then(setUser).catch(() => setUser(null));
  }, []);

  if (user === undefined) {
    return <p style={{ padding: 24, color: color.gray }}>불러오는 중…</p>;
  }

  const gate = (el: JSX.Element) => (user ? el : <Navigate to="/login" replace />);

  return (
    <Routes>
      <Route path="/login" element={<Login onLogin={setUser} />} />
      <Route path="/mypage" element={gate(<MyPage user={user!} onLogout={() => setUser(null)} />)} />
      <Route path="/consulting" element={gate(<Consulting />)} />
      <Route path="/live" element={gate(<Live />)} />
      <Route path="*" element={<Navigate to={user ? "/mypage" : "/login"} replace />} />
    </Routes>
  );
}
