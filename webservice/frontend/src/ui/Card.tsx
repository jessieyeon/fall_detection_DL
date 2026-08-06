import type { CSSProperties, ReactNode } from "react";
import { color, radius, shadow } from "../theme";

type Props = {
  pad?: number;
  bg?: string;
  /** 그림자를 한 단계 올린다(강조 카드) */
  raised?: boolean;
  style?: CSSProperties;
  children?: ReactNode;
  /** @deprecated 예전 outline 두께 인자. 무시된다. */
  outlineW?: number;
  [k: string]: unknown;
};

export default function Card({
  pad = 18, bg = color.surface, raised, style, children, outlineW: _ignored, ...rest
}: Props) {
  return (
    <div
      style={{
        background: bg,
        padding: pad,
        border: `1px solid ${color.line}`,
        borderRadius: radius.lg,
        boxShadow: raised ? shadow.raised : shadow.card,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}
