import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { color, font, radius } from "../theme";
import { useIsMobile } from "../useMedia";
import { Shield, Clipboard, Video, Person } from "./icons";

type Tab = "consult" | "monitor" | "mypage";

const NAV: {
  tab: Tab; to: string; label: string;
  Icon: (p: { size?: number; color?: string }) => JSX.Element;
}[] = [
  { tab: "consult", to: "/consulting", label: "컨설팅", Icon: Clipboard },
  { tab: "monitor", to: "/live", label: "실시간", Icon: Video },
  { tab: "mypage", to: "/mypage", label: "마이페이지", Icon: Person },
];

function Brand({ compact }: { compact?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
      <span style={{
        width: 28, height: 28, borderRadius: 8, background: color.brand,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      }}>
        <Shield size={16} color={color.white} />
      </span>
      {!compact && (
        <span style={{ fontSize: font.h2, fontWeight: 700, letterSpacing: -0.2 }}>
          다온 안전지킴이
        </span>
      )}
    </div>
  );
}

/**
 * 레이아웃 컨테이너.
 *
 * 모바일(≤768px): 상단 헤더 + 하단 탭바, 단일 컬럼.
 * 데스크톱: 좌측 사이드바 + 여백을 살린 본문. 전시 사이트가 iframe 으로 넣으면
 * 폭이 좁아질 수 있어, 창 크기가 아니라 문서 뷰포트를 보는 matchMedia 로
 * 분기한다(useIsMobile 참고).
 */
export default function AppShell({
  active, right, children,
}: { active: Tab; right?: ReactNode; children: ReactNode }) {
  const mobile = useIsMobile();

  if (mobile) {
    return (
      <div style={{ minHeight: "100%", background: color.bg, display: "flex", flexDirection: "column" }}>
        <header style={{
          position: "sticky", top: 0, zIndex: 5, height: 52, padding: "0 16px",
          background: color.surface, borderBottom: `1px solid ${color.line}`,
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <Brand />
          {right && <div style={{ display: "flex", alignItems: "center" }}>{right}</div>}
        </header>

        <main style={{
          flex: 1, padding: "16px 16px 88px",
          display: "flex", flexDirection: "column", gap: 20,
        }}>
          {children}
        </main>

        <nav style={{
          position: "fixed", left: 0, right: 0, bottom: 0, height: 62,
          background: color.surface, borderTop: `1px solid ${color.line}`,
          display: "flex", zIndex: 10,
        }}>
          {NAV.map(({ tab, to, label, Icon }) => {
            const on = tab === active;
            return (
              <Link key={tab} to={to} data-tour={`nav-${tab}`} style={{
                flex: 1, display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center", gap: 3,
                textDecoration: "none",
                color: on ? color.brand : color.inkFaint,
              }}>
                <Icon size={19} />
                <span style={{ fontSize: font.caption, fontWeight: on ? 700 : 500 }}>{label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100%", background: color.bg, display: "flex" }}>
      <aside style={{
        width: 216, flexShrink: 0, background: color.surface,
        borderRight: `1px solid ${color.line}`,
        padding: "18px 12px", display: "flex", flexDirection: "column", gap: 22,
        position: "sticky", top: 0, alignSelf: "flex-start", height: "100vh",
      }}>
        <div style={{ padding: "0 6px" }}><Brand /></div>
        <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {NAV.map(({ tab, to, label, Icon }) => {
            const on = tab === active;
            return (
              <Link key={tab} to={to} data-tour={`nav-${tab}`} style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "9px 12px", borderRadius: radius.md,
                textDecoration: "none", fontSize: font.body,
                fontWeight: on ? 700 : 500,
                background: on ? color.brandTint : "transparent",
                color: on ? color.brand : color.inkSoft,
              }}>
                <Icon size={17} />
                {label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        {right && (
          <header style={{
            height: 56, padding: "0 28px", background: color.surface,
            borderBottom: `1px solid ${color.line}`,
            display: "flex", alignItems: "center", justifyContent: "flex-end",
          }}>
            {right}
          </header>
        )}
        <main style={{
          flex: 1, width: "100%", maxWidth: 1040, margin: "0 auto",
          padding: "28px 28px 48px",
          display: "flex", flexDirection: "column", gap: 26,
        }}>
          {children}
        </main>
      </div>
    </div>
  );
}
