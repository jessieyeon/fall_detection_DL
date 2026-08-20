import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { initAnalytics, track, EVENTS } from "./analytics";
import "./index.css";

// 계측 초기화는 렌더를 **기다리지 않는다.** await 로 붙이면 /api/config 가
// 느리거나 막힌 순간 관람객이 흰 화면을 보게 된다 — 통계를 얻자고 앱을
// 인질로 잡는 셈이다. 백그라운드로 돌리고, 준비되면 그때부터 이벤트를 보낸다.
initAnalytics().then(() => track(EVENTS.APP_OPEN));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);
