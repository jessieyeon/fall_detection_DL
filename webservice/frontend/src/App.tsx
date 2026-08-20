import { useEffect, useState } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { me, type User } from "./api";
import { color } from "./theme";
import { getFlag, setFlag, TOUR_SEEN } from "./storage";
import { track, trackPageview, EVENTS } from "./analytics";
import Login from "./pages/Login";
import MyPage from "./pages/MyPage";
import Consulting from "./pages/Consulting";
import Live from "./pages/Live";
import Tour from "./ui/Tour";


export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined); // undefined=확인중
  const [showTour, setShowTour] = useState(false);
  const loc = useLocation();

  useEffect(() => {
    me().then(setUser).catch(() => setUser(null));
  }, []);

  // SPA 는 주소가 바뀌어도 페이지 로드가 없다. PostHog 의 자동 페이지뷰를 끄고
  // (analytics.ts 참고) 여기서 라우트마다 직접 보낸다 — 이게 없으면 퍼널의
  // 모든 단계가 첫 화면 하나로 뭉쳐 보인다.
  useEffect(() => { trackPageview(loc.pathname); }, [loc.pathname]);

  // '실시간(AI 세션)' 진입은 퍼널의 마지막 단계라 따로 센다.
  useEffect(() => {
    if (loc.pathname === "/live") track(EVENTS.LIVE_OPEN);
  }, [loc.pathname]);

  /**
   * 앱 소개는 로그인 화면을 벗어나는 순간 뜬다.
   *
   * 예전에는 컨설팅 페이지 안에 있었다. 그래서 '체험하기'로 들어와도 관람객이
   * 마이페이지에 먼저 닿으면 소개를 못 보고, 컨설팅 탭을 눌러야 나타났다.
   * 어느 화면으로 들어오든 처음 한 번은 무엇을 하는 앱인지 알려주는 게 맞다.
   */
  useEffect(() => {
    if (!user || loc.pathname === "/login") return;
    if (getFlag(TOUR_SEEN) === "1") return;
    setShowTour(true);
    track(EVENTS.TOUR_SHOWN, { from: loc.pathname });
  }, [user, loc.pathname]);

  const closeTour = () => {
    setShowTour(false);
    setFlag(TOUR_SEEN, "1");
    track(EVENTS.TOUR_DONE);
  };

  if (user === undefined) {
    return <p style={{ padding: 24, color: color.gray }}>불러오는 중…</p>;
  }

  const gate = (el: JSX.Element) => (user ? el : <Navigate to="/login" replace />);

  return (
    <>
      <Routes>
        <Route path="/login" element={<Login onLogin={setUser} />} />
        <Route path="/mypage" element={gate(<MyPage user={user!} onLogout={() => setUser(null)} />)} />
        <Route path="/consulting" element={gate(<Consulting onOpenTour={() => setShowTour(true)} />)} />
        <Route path="/live" element={gate(<Live />)} />
        <Route path="*" element={<Navigate to={user ? "/consulting" : "/login"} replace />} />
      </Routes>
      {showTour && user && <Tour onClose={closeTour} />}
    </>
  );
}
