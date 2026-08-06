import type { CSSProperties, ReactNode } from "react";
import { color, radius, shadow, font } from "../theme";

type Variant = "primary" | "outline" | "ghost" | "danger";
type Props = {
  variant?: Variant;
  big?: boolean;
  full?: boolean;
  icon?: ReactNode;
  children?: ReactNode;
  as?: "button" | "label" | "a";
  disabled?: boolean;
  style?: CSSProperties;
  [k: string]: unknown;
};

const skin: Record<Variant, CSSProperties> = {
  primary: {
    background: color.brand,
    color: color.white,
    border: "1px solid transparent",
    boxShadow: shadow.brand,
  },
  outline: {
    background: color.white,
    color: color.brand,
    border: `1px solid ${color.lineStrong}`,
  },
  ghost: {
    background: "transparent",
    color: color.inkSoft,
    border: "1px solid transparent",
  },
  danger: {
    background: color.red,
    color: color.white,
    border: "1px solid transparent",
  },
};

export default function Button({
  variant = "primary", big, full, icon, children, as = "button",
  disabled, style, ...rest
}: Props) {
  const El = as as "button";
  return (
    <El
      disabled={as === "button" ? disabled : undefined}
      style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        gap: 8,
        padding: big ? "13px 20px" : "9px 14px",
        width: full ? "100%" : undefined,
        fontSize: big ? font.h2 : font.body,
        fontWeight: 600,
        lineHeight: 1.3,
        borderRadius: radius.md,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        transition: "filter .15s, box-shadow .15s",
        ...skin[variant],
        ...style,
      }}
      {...rest}
    >
      {icon}
      {children}
    </El>
  );
}
