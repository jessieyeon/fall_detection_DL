import type { ReactNode } from "react";
import { color, font } from "../theme";

type Props = {
  title?: string;
  /** 제목 옆 보조 설명 */
  hint?: string;
  titleColor?: string;
  gap?: number;
  children?: ReactNode;
  /** @deprecated 예전 굵은 구분선. 새 디자인에서는 카드 간격으로 구분한다. */
  divider?: boolean;
};

export default function Section({
  title, hint, titleColor = color.ink, gap = 12, children,
}: Props) {
  return (
    <section style={{ display: "flex", flexDirection: "column", gap }}>
      {title && (
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, fontSize: font.h2, fontWeight: 700, color: titleColor }}>
            {title}
          </h2>
          {hint && (
            <span style={{ fontSize: font.caption, color: color.inkFaint }}>{hint}</span>
          )}
        </div>
      )}
      {children}
    </section>
  );
}
