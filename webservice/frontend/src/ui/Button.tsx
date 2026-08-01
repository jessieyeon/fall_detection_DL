import type { CSSProperties, ReactNode } from "react";
import { color, edge } from "../theme";

type Variant = "primary" | "outline" | "danger";
type Props = {
  variant?: Variant;
  big?: boolean;
  full?: boolean;
  icon?: ReactNode;
  children?: ReactNode;
  as?: "button" | "label" | "a";
  style?: CSSProperties;
  [k: string]: unknown;
};

const bg: Record<Variant, string> = { primary: color.black, outline: color.white, danger: color.red };
const fg: Record<Variant, string> = { primary: color.white, outline: color.ink, danger: color.white };

export default function Button({ variant = "primary", big, full, icon, children, as = "button", style, ...rest }: Props) {
  const El = as as "button";
  return (
    <El
      style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 10,
        padding: big ? "18px 24px" : "10px 16px",
        width: full ? "100%" : undefined,
        background: bg[variant], color: fg[variant],
        fontSize: big ? 22 : 16, fontWeight: 700, lineHeight: 1.25, letterSpacing: 0.3,
        ...(variant === "outline" ? edge(2) : {}),
        ...style,
      }}
      {...rest}
    >
      {icon}
      {children}
    </El>
  );
}
