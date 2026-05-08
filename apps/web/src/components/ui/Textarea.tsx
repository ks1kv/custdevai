import { forwardRef, type TextareaHTMLAttributes, type ReactNode } from "react";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, hint, error, id, style, ...rest }, ref) => (
    <div className="field">
      {label && <label htmlFor={id}>{label}</label>}
      <textarea
        {...rest}
        id={id}
        ref={ref}
        rows={rest.rows ?? 4}
        style={{
          border: "1px solid",
          borderColor: error ? "var(--c-danger)" : "var(--c-border)",
          borderRadius: 6,
          padding: "8px 10px",
          background: "var(--c-surface)",
          fontSize: 14,
          fontFamily: "inherit",
          resize: "vertical",
          ...style,
        }}
      />
      {hint && !error && <span className="hint">{hint}</span>}
      {error && <span className="error">{error}</span>}
    </div>
  ),
);
Textarea.displayName = "Textarea";
