import type { CSSProperties, ReactNode } from "react";
import { color, edge } from "../theme";

type Props = {
  pad?: number;
  outlineW?: number;
  bg?: string;
  style?: CSSProperties;
  children?: ReactNode;
  [k: string]: unknown;
};

export default function Card({ pad = 24, outlineW = 2, bg = color.white, style, children, ...rest }: Props) {
  return (
    <div style={{ background: bg, padding: pad, ...edge(outlineW), ...style }} {...rest}>
      {children}
    </div>
  );
}
