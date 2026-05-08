import { t } from "@/lib/locales/ru";

export function Spinner({ inline = false }: { inline?: boolean }) {
  return (
    <div
      role="status"
      aria-label={t.common.loading}
      style={{
        display: inline ? "inline-flex" : "flex",
        justifyContent: "center",
        alignItems: "center",
        padding: inline ? 0 : 24,
        color: "var(--c-muted)",
      }}
    >
      {t.common.loading}
    </div>
  );
}
