/**
 * CampaignCompareView — сравнение двух кампаний (FR-WEB-08).
 * Phase 4: чтение метаданных и счётчиков сессий через GET /campaigns/{id}.
 * Полное сравнение распределения тональности и тем — после Phase 5
 * /transcripts API.
 */

import { useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { getCampaign } from "@/api/campaigns";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import {
  AnalysisStatusBadge,
  CampaignStatusBadge,
} from "@/components/StatusBadge";
import { t } from "@/lib/locales/ru";

export function CampaignComparePage() {
  const [params, setParams] = useSearchParams();
  const [a, setA] = useState(params.get("a") ?? "");
  const [b, setB] = useState(params.get("b") ?? "");

  const ids = [Number(a), Number(b)].filter((n) => Number.isFinite(n) && n > 0);

  const queries = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["campaign", id],
      queryFn: () => getCampaign(id),
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
            {q.data && (
              <>
                <p>
                  <strong>{q.data.title}</strong>
                </p>
                <p>
                  <CampaignStatusBadge status={q.data.status} />{" "}
                  <AnalysisStatusBadge status={q.data.analysis_status} />
                </p>
                <p className="muted">{q.data.description ?? "—"}</p>
                <p>
                  Цель тем: {q.data.target_topic_count}
                </p>
              </>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
