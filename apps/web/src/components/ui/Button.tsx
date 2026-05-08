/**
 * Минимальный Button-компонент в стиле shadcn/ui.
 * Варианты: primary (CTA), secondary, ghost, danger.
 */

import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const baseStyle: React.CSSProperties = {
  border: "1px solid transparent",
  borderRadius: 6,
  fontWeight: 500,
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  transition: "background 0.15s, border-color 0.15s",
};

const sizeStyle: Record<Size, React.CSSProperties> = {
  sm: { padding: "4px 10px", fontSize: 13 },
  md: { padding: "8px 16px", fontSize: 14 },
};

const variantStyle: Record<Variant, React.CSSProperties> = {
  primary: { background: "var(--c-primary)", color: "#fff" },
  secondary: {
    background: "var(--c-surface)",
    color: "var(--c-text)",
    borderColor: "var(--c-border)",
  },
  ghost: { background: "transparent", color: "var(--c-text)" },
  danger: { background: "var(--c-danger)", color: "#fff" },
};

export function Button({
  variant = "primary",
  size = "md",
  loading,
  disabled,
  style,
  children,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <button
      {...rest}
      disabled={isDisabled}
      style={{
        ...baseStyle,
        ...sizeStyle[size],
        ...variantStyle[variant],
        opacity: isDisabled ? 0.6 : 1,
        cursor: isDisabled ? "not-allowed" : "pointer",
        ...style,
      }}
    >
      {loading ? "…" : children}
    </button>
  );
}
