/**
 * TranscriptsTab — таб «Транскрипты» с поиском и фильтром по тональности
 * (FR-WEB-05). Использует /api/v1/campaigns/{id}/transcripts.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { listTranscripts } from "@/api/campaigns";
import type { SentimentLabel } from "@/api/types";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { t } from "@/lib/locales/ru";

const SENTIMENT_LABELS: Array<{ value: SentimentLabel | ""; label: string }> = [
  { value: "", label: "— любая —" },
  { value: "positive", label: "Позитивная" },
  { value: "neutral", label: "Нейтральная" },
  { value: "negative", label: "Негативная" },
  { value: "low_confidence", label: "Низкая уверенность" },
];

export function TranscriptsTab({ campaignId }: { campaignId: number }) {
  const [search, setSearch] = useState("");
  const [sentiment, setSentiment] = useState<SentimentLabel | "">("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["transcripts", campaignId, search, sentiment],
    queryFn: () =>
      listTranscripts(campaignId, {
        q: search.trim() || undefined,
        sentiment: sentiment || undefined,
        limit: 50,
      }),
  });

  return (
    <Card>
      <div className="toolbar" style={{ marginBottom: 12 }}>
        <Input
          label="Поиск по тексту"
          placeholder="например: поиск"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 260 }}
        />
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="sentiment-filter">Тональность</label>
          <select
            id="sentiment-filter"
            value={sentiment}
            onChange={(e) => setSentiment(e.target.value as SentimentLabel | "")}
            style={{
              border: "1px solid var(--c-border)",
              borderRadius: 6,
              padding: "8px 10px",
              background: "var(--c-surface)",
            }}
          >
            {SENTIMENT_LABELS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isLoading && <Spinner />}
      {error && <div className="danger">{t.errors.network}</div>}

      {data && data.items.length === 0 && (
        <p className="muted">
          Сессий не найдено. Уточните поиск или дождитесь завершения интервью.
        </p>
      )}

      {data && data.items.length > 0 && (
        <div>
          <p className="muted" style={{ marginTop: 0 }}>
            Найдено сессий: {data.total}
          </p>
          {data.items.map((s) => (
            <details
              key={s.session_id}
              style={{
                border: "1px solid var(--c-border)",
                borderRadius: 6,
                padding: "8px 12px",
                marginBottom: 8,
              }}
            >
              <summary style={{ cursor: "pointer", fontWeight: 500 }}>
                {s.pseudonym}
                <span className="muted" style={{ marginLeft: 8 }}>
                  · ответов: {s.answers.length}
                  {s.completed_at && (
                    <> · {new Date(s.completed_at).toLocaleString("ru")}</>
                  )}
                </span>
              </summary>
              <table style={{ marginTop: 8 }}>
                <thead>
                  <tr>
                    <th style={{ width: 40 }}>#</th>
                    <th>Вопрос</th>
                    <th>Ответ</th>
                    <th>Тональность</th>
                  </tr>
                </thead>
                <tbody>
                  {s.answers.map((a) => (
                    <tr key={a.question_id}>
                      <td>{a.question_order + 1}</td>
                      <td>{a.question_text}</td>
                      <td>{a.answer_text}</td>
                      <td>
                        {a.sentiment_label ? (
                          <span className={`badge ${a.sentiment_label}`}>
                            {SENTIMENT_LABELS.find(
                              (o) => o.value === a.sentiment_label,
                            )?.label ?? a.sentiment_label}
                          </span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          ))}
        </div>
      )}
    </Card>
  );
}
