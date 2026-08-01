import type { ReactNode } from "react";
import { color } from "../theme";

type Props = {
  title?: string;
  titleColor?: string;
  divider?: boolean;
  gap?: number;
  children?: ReactNode;
};

export default function Section({ title, titleColor = color.ink, divider = true, gap = 16, children }: Props) {
  return (
    <section
      style={{
        display: "flex", flexDirection: "column", gap,
        paddingTop: divider ? 24 : 0,
        borderTop: divider ? `4px solid ${color.black}` : undefined,
      }}
    >
      {title && <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: titleColor }}>{title}</h2>}
      {children}
    </section>
  );
}
