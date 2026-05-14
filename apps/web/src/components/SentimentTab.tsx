/**
 * SentimentTab — таб «Тональность» с агрегатом из /transcripts (FR-WEB-06).
 * Считает распределение по транскриптам и рисует Recharts PieChart.
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { listTranscripts } from "@/api/campaigns";
import type { SentimentLabel } from "@/api/types";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";

const LABEL_RU: Record<SentimentLabel, string> = {
  positive: "Позитивная",
  neutral: "Нейтральная",
  negative: "Негативная",
  low_confidence: "Низкая уверенность",
};

const COLOR: Record<SentimentLabel, string> = {
  positive: "#15803d",
  neutral: "#6b7280",
  negative: "#b91c1c",
  low_confidence: "#b45309",
};

export function SentimentTab({ campaignId }: { campaignId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["transcripts", campaignId, "_all"],
    queryFn: () => listTranscripts(campaignId, { limit: 100 }),
  });

  const distribution = useMemo(() => {
    const counts = new Map<SentimentLabel, number>();
    for (const s of data?.items ?? []) {
      for (const a of s.answers) {
        if (a.sentiment_label) {
          counts.set(a.sentiment_label, (counts.get(a.sentiment_label) ?? 0) + 1);
        }
      }
    }
    return Array.from(counts.entries()).map(([label, count]) => ({
      label,
      name: LABEL_RU[label],
      value: count,
    }));
  }, [data]);

  if (isLoading) return <Spinner />;
  if (!data || distribution.length === 0) {
    return (
      <Card>
        <p className="muted">
          Распределение тональности станет доступным после завершения ML-анализа.
          Запустите анализ во вкладке «Обзор».
        </p>
      </Card>
    );
  }

  return (
    <Card title="Распределение тональности по ответам">
      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveContainer>
          <PieChart>
            <Pie data={distribution} dataKey="value" nameKey="name" outerRadius={120} label>
              {distribution.map((entry) => (
                <Cell key={entry.label} fill={COLOR[entry.label]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
