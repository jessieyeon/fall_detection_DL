import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { color } from "../theme";
import { Shield, Clipboard, Video, Person } from "./icons";

type Tab = "consult" | "monitor" | "mypage";

const NAV: { tab: Tab; to: string; label: string; Icon: (p: { size?: number; color?: string }) => JSX.Element }[] = [
  { tab: "consult", to: "/consulting", label: "Consult", Icon: Clipboard },
  { tab: "monitor", to: "/live", label: "Monitor", Icon: Video },
  { tab: "mypage", to: "/mypage", label: "My Page", Icon: Person },
];

export default function AppShell({ active, right, children }: { active: Tab; right?: ReactNode; children: ReactNode }) {
  return (
    <div style={{ minHeight: "100%", maxWidth: 480, margin: "0 auto", background: color.bg, display: "flex", flexDirection: "column", position: "relative" }}>
      <header style={{ position: "sticky", top: 0, zIndex: 5, height: 48, padding: "0 20px", background: color.bg, borderBottom: `2px solid ${color.black}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Shield size={20} />
          <span style={{ fontSize: 22, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.3 }}>Safety Advisor</span>
        </div>
        {right && <div style={{ display: "flex", alignItems: "center", color: color.ink }}>{right}</div>}
      </header>

      <main style={{ flex: 1, padding: "32px 20px 104px", display: "flex", flexDirection: "column", gap: 32 }}>{children}</main>

      <nav style={{ position: "fixed", left: 0, right: 0, bottom: 0, maxWidth: 480, margin: "0 auto", height: 72, background: color.bg, borderTop: `2px solid ${color.black}`, display: "flex" }}>
        {NAV.map(({ tab, to, label, Icon }) => {
          const on = tab === active;
          return (
            <Link key={tab} to={to} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 4, textDecoration: "none", background: on ? color.black : "transparent", color: on ? color.white : color.black }}>
              <Icon size={20} />
              <span style={{ fontSize: 15, fontWeight: 700 }}>{label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
