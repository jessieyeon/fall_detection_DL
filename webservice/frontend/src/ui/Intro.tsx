import { color, font, radius } from "../theme";
import { useIsMobile } from "../useMedia";
import { Video, Clipboard, Shield } from "./icons";
import Card from "./Card";

/**
 * 앱 소개 모듈.
 *
 * 온라인 전시 관람객은 이 앱을 처음 보고, 대개 10초 안에 계속 볼지 결정한다.
 * "무엇을 하는 앱인지 → 어떻게 쓰는지 → 왜 이 방식인지"를 그 안에 넣는다.
 *
 * 화면을 막는 모달이 아니라 접을 수 있는 카드로 둔 이유: 전시장에서 모달을
 * 닫는 동작 하나가 이탈 지점이 된다. 읽고 싶으면 읽고 아니면 바로 아래
 * 체험으로 갈 수 있어야 한다.
 */

// 게임 튜토리얼처럼 '이 버튼을 누르면 무엇이 나오는지'를 알려주는 안내.
// 항목은 두 서비스만 — 안내가 길어지면 아무도 읽지 않는다.
const GUIDES = [
  {
    Icon: Clipboard,
    title: "컨설팅",
    body: "생활 영상을 올려주시면 동선을 분석해 안전 타일이 어디에 필요한지 알려드립니다.",
    hint: "생활 영상 수집이 어려운 온라인 체험에서는, 미리 준비된 체험용 영상으로 분석 결과를 바로 볼 수 있어요.",
  },
  {
    Icon: Video,
    title: "실시간",
    body: "카메라를 연결하면 AI가 인식한 자세(스켈레톤)를 실시간으로 볼 수 있습니다.",
    hint: "카메라 연결은 다온 카메라가 설치된 환경에서만 가능해요. 준비되지 않았다면 데모 영상으로 확인해주세요.",
  },
];

export default function Intro({ onClose }: { onClose: () => void }) {
  const mobile = useIsMobile();

  return (
    <Card raised style={{ display: "flex", flexDirection: "column", gap: 16, padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
        <div>
          <div style={{ fontSize: font.h2, fontWeight: 700 }}>
            다온 안전지킴이 체험에 오신 것을 환영합니다
          </div>
          <p style={{
            margin: "6px 0 0", fontSize: font.small, color: color.inkSoft, lineHeight: 1.65,
          }}>
            다온 안전지킴이는 어르신의 안전한 일상을 위해 <b>컨설팅</b>과{" "}
            <b>실시간 감지</b>를 제공하는 <b>시설 관리자용 앱</b>입니다.
            세대 내부부터 공용 라운지·복도까지, 어르신이 지나다니는 곳의 위험을
            미리 확인하고 대비할 수 있어요.
          </p>
        </div>
        <button onClick={onClose} aria-label="소개 닫기" style={{
          alignSelf: "flex-start", flexShrink: 0,
          fontSize: font.caption, color: color.inkFaint, padding: "2px 6px",
        }}>
          닫기
        </button>
      </div>

      <div style={{
        display: "grid", gap: 10,
        gridTemplateColumns: mobile ? "1fr" : "repeat(2, 1fr)",
      }}>
        {GUIDES.map(({ Icon, title, body, hint }) => (
          <div key={title} style={{
            display: "flex", flexDirection: "column", gap: 8,
            padding: 14, background: color.bg, borderRadius: radius.md,
          }}>
            <div style={{ display: "flex", gap: 9, alignItems: "center" }}>
              <span style={{
                width: 28, height: 28, flexShrink: 0, borderRadius: 8,
                background: color.brand,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <Icon size={14} color={color.white} />
              </span>
              <span style={{ fontSize: font.small, fontWeight: 700 }}>{title}</span>
            </div>
            <div style={{ fontSize: font.caption, color: color.ink, lineHeight: 1.65 }}>
              {body}
            </div>
            <div style={{
              fontSize: font.caption, color: color.inkSoft, lineHeight: 1.6,
              paddingTop: 7, borderTop: `1px dashed ${color.line}`,
            }}>
              {hint}
            </div>
          </div>
        ))}
      </div>

      {/* 근거 한 줄. '왜 하필 동선인가'에 대한 답이자 이 제품의 차별점이다. */}
      <div style={{
        display: "flex", gap: 10, alignItems: "flex-start",
        padding: "12px 14px", background: color.brandTint, borderRadius: radius.md,
      }}>
        <span style={{
          fontSize: font.caption, fontWeight: 700, color: color.brand,
          whiteSpace: "nowrap", paddingTop: 1,
        }}>
          왜 동선인가요?
        </span>
        <span style={{ fontSize: font.caption, color: color.ink, lineHeight: 1.7 }}>
          고령자 안전사고의 <b>62.7%가 낙상</b>이고, 그 낙상의 <b>74.8%가 생활공간
          안</b>에서 일어납니다. 특정 공간이 더 위험해서가 아니라, 매일 지나다니는
          곳이기 때문입니다. 다온은 실제 생활 동선을 재서{" "}
          <b>어디를 먼저 손봐야 하는지</b> 알려드립니다.
        </span>
      </div>
    </Card>
  );
}
