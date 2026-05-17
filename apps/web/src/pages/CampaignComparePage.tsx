/**
 * CampaignCompareView — сравнение двух кампаний (FR-WEB-08).
 * Phase 5: добавлены распределение тональности и топ-темы из лёгкого
 * endpoint /campaigns/{id}/summary.
 */

import { useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { getCampaignSummary } from "@/api/campaigns";
import type {
  CampaignSummaryOut,
  SentimentLabel as SentimentLabelType,
} from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import {
  AnalysisStatusBadge,
  CampaignStatusBadge,
} from "@/components/StatusBadge";
import { t } from "@/lib/locales/ru";

const SENTIMENT_RU: Record<SentimentLabelType, string> = {
  positive: "Позитивная",
  neutral: "Нейтральная",
  negative: "Негативная",
  low_confidence: "Низкая уверенность",
};
const SENTIMENT_ORDER: SentimentLabelType[] = [
  "positive",
  "neutral",
  "negative",
  "low_confidence",
];

export function CampaignComparePage() {
  const [params, setParams] = useSearchParams();
  const [a, setA] = useState(params.get("a") ?? "");
  const [b, setB] = useState(params.get("b") ?? "");

  const ids = [Number(a), Number(b)].filter((n) => Number.isFinite(n) && n > 0);

  const queries = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["campaign", id, "summary"],
      queryFn: () => getCampaignSummary(id),
    })),
  });

  return (
    <div>
      <div className="page-header">
        <h2>{t.nav.compare}</h2>
      </div>

      <Card>
        <div className="toolbar">
          <Input
            label="Кампания A (id)"
            type="number"
            value={a}
            onChange={(e) => setA(e.target.value)}
            style={{ width: 100 }}
          />
          <Input
            label="Кампания B (id)"
            type="number"
            value={b}
            onChange={(e) => setB(e.target.value)}
            style={{ width: 100 }}
          />
          <Button
            onClick={() => setParams({ a, b })}
            disabled={!a || !b}
          >
            Сравнить
          </Button>
        </div>
      </Card>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16,
          marginTop: 16,
        }}
      >
        {queries.map((q, i) => (
          <Card key={i} title={`Кампания ${i === 0 ? "A" : "B"}`}>
            {q.isLoading && "Загрузка…"}
            {q.error && <span className="danger">{t.errors.notFound}</span>}
            {q.data && <SummaryBody summary={q.data} />}
          </Card>
        ))}
      </div>
    </div>
  );
}

function SummaryBody({ summary }: { summary: CampaignSummaryOut }) {
  const totalAnswers = Object.values(summary.sentiment_distribution).reduce(
    (s, v) => s + v,
    0,
  );
  return (
    <>
      <p>
        <strong>{summary.title}</strong>
      </p>
      <p>
        <CampaignStatusBadge status={summary.status} />{" "}
        <AnalysisStatusBadge status={summary.analysis_status} />
      </p>
      <p className="muted">{summary.description ?? "—"}</p>
      <p>
        Сессий: <strong>{summary.sessions_completed}</strong> /{" "}
        {summary.sessions_total} (завершено), ответов:{" "}
        <strong>{summary.answers_total}</strong>, цель тем:{" "}
        {summary.target_topic_count}
      </p>

      <h3 style={{ marginTop: 16, marginBottom: 8 }}>Тональность</h3>
      {totalAnswers === 0 ? (
        <p className="muted">Нет данных</p>
      ) : (
        <table>
          <tbody>
            {SENTIMENT_ORDER.filter(
              (l) => (summary.sentiment_distribution[l] ?? 0) > 0,
            ).map((label) => {
              const count = summary.sentiment_distribution[label] ?? 0;
              const pct = Math.round((count / totalAnswers) * 100);
              return (
                <tr key={label}>
                  <td>{SENTIMENT_RU[label]}</td>
                  <td>
                    {count} ({pct}%)
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <h3 style={{ marginTop: 16, marginBottom: 8 }}>Топ-темы</h3>
      {summary.topics_top.length === 0 ? (
        <p className="muted">Темы не выявлены</p>
      ) : (
        <ol style={{ paddingLeft: 20, margin: 0 }}>
          {summary.topics_top.map((topic, idx) => {
            const heading =
              topic.label ||
              topic.keywords.slice(0, 3).join(" / ") ||
              `Тема ${idx + 1}`;
            return (
              <li key={idx} style={{ marginBottom: 6 }}>
                <strong>{heading}</strong>{" "}
                <span className="muted">
                  ({topic.frequency_count} ответов)
                </span>
                {topic.keywords.length > 0 && (
                  <div className="muted" style={{ fontSize: 13 }}>
                    {topic.keywords.slice(0, 8).join(", ")}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </>
  );
}
