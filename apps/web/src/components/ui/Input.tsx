/**
 * Input — accessible-обёртка над <input> с label/error/hint.
 * forwardRef нужен для интеграции с react-hook-form register().
 */

import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
}

const inputStyle: React.CSSProperties = {
  border: "1px solid var(--c-border)",
  borderRadius: 6,
  padding: "8px 10px",
  background: "var(--c-surface)",
  fontSize: 14,
  outline: "none",
};

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, hint, error, id, style, ...rest }, ref) => {
    return (
      <div className="field">
        {label && <label htmlFor={id}>{label}</label>}
        <input
          {...rest}
          id={id}
          ref={ref}
          style={{
            ...inputStyle,
            borderColor: error ? "var(--c-danger)" : "var(--c-border)",
            ...style,
          }}
        />
        {hint && !error && <span className="hint">{hint}</span>}
        {error && <span className="error">{error}</span>}
      </div>
    );
  },
);
Input.displayName = "Input";
