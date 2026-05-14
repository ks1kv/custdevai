/**
 * CampaignDetailPage — детали кампании с вкладками:
 *   - Обзор (FR-WEB-04, кнопка запустить ML-анализ FR-API-04)
 *   - Транскрипты (FR-WEB-05, поиск + псевдонимы)
 *   - Тональность (FR-WEB-06, Recharts pie)
 *   - Темы (FR-WEB-07, Recharts hbar)
 *   - Отчёты (ссылка на /reports)
 *
 * Транскрипты, тональность и темы в Phase 4 заполняются заглушкой
 * "Раздел будет доступен после публикации API эндпоинта /transcripts".
 * Phase 5 расширяет API; SPA уже готов потреблять.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import {
  getAnalysisStatus,
  getCampaign,
  startAnalysis,
} from "@/api/campaigns";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import {
  AnalysisStatusBadge,
  CampaignStatusBadge,
} from "@/components/StatusBadge";
import { SentimentTab } from "@/components/SentimentTab";
import { TranscriptsTab } from "@/components/TranscriptsTab";
import { t } from "@/lib/locales/ru";

type TabKey = "overview" | "transcripts" | "sentiment" | "topics" | "reports";

export function CampaignDetailPage() {
  const { id } = useParams();
  const campaignId = Number(id);
  const [tab, setTab] = useState<TabKey>("overview");
  const queryClient = useQueryClient();

  const { data: campaign, isLoading } = useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: () => getCampaign(campaignId),
    refetchInterval: 10_000,
  });

  const { data: analysisStatus } = useQuery({
    queryKey: ["campaign", campaignId, "analysis-status"],
    queryFn: () => getAnalysisStatus(campaignId),
    refetchInterval: 5_000,
  });

  const analyze = useMutation({
    mutationFn: () => startAnalysis(campaignId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaign", campaignId] });
    },
  });

  if (isLoading || !campaign) return <Spinner />;

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 style={{ marginBottom: 4 }}>{campaign.title}</h2>
          <div className="toolbar">
            <CampaignStatusBadge status={campaign.status} />
            <AnalysisStatusBadge status={campaign.analysis_status} />
            <span className="muted">
              {t.campaign.targetTopicCount.split("(")[0].trim()}: {campaign.target_topic_count}
            </span>
          </div>
        </div>
        <Link to={`/campaigns/${campaignId}/reports`}>
          <Button variant="secondary">{t.campaign.tabs.reports}</Button>
        </Link>
      </div>

      <div className="tabs">
        {(["overview", "transcripts", "sentiment", "topics", "reports"] as const).map(
          (key) => (
            <button
              key={key}
              className={tab === key ? "active" : ""}
              onClick={() => setTab(key)}
            >
              {t.campaign.tabs[key]}
            </button>
          ),
        )}
      </div>

      {tab === "overview" && (
        <Card>
          <p className="muted">{campaign.description || "Описание не задано"}</p>
          {campaign.invitation_url && (
            <p>
              <strong>Ссылка-приглашение:</strong>{" "}
              <code>{campaign.invitation_url}</code>
            </p>
          )}
          <hr style={{ margin: "16px 0", border: 0, borderTop: "1px solid var(--c-border)" }} />
          <h4>ML-анализ</h4>
          {analysisStatus && (
            <ul style={{ margin: "8px 0", paddingLeft: 20 }}>
              <li>Статус: <AnalysisStatusBadge status={analysisStatus.analysis_status} /></li>
              {analysisStatus.analysis_started_at && (
                <li>Запущен: {new Date(analysisStatus.analysis_started_at).toLocaleString("ru")}</li>
              )}
              {analysisStatus.analysis_completed_at && (
                <li>Завершён: {new Date(analysisStatus.analysis_completed_at).toLocaleString("ru")}</li>
              )}
              {analysisStatus.analysis_error && (
                <li className="danger">Ошибка: {analysisStatus.analysis_error}</li>
              )}
            </ul>
          )}
          <Button
            onClick={() => analyze.mutate()}
            loading={analyze.isPending}
            disabled={analysisStatus?.analysis_status === "running"}
          >
            {t.campaign.runAnalysis}
          </Button>
          {analyze.error && analyze.error instanceof ApiError && (
            <div className="danger" style={{ marginTop: 8 }}>
              {analyze.error.problem.detail || analyze.error.problem.title}
            </div>
          )}
        </Card>
      )}

      {tab === "transcripts" && <TranscriptsTab campaignId={campaignId} />}

      {tab === "sentiment" && <SentimentTab campaignId={campaignId} />}

      {tab === "topics" && (
        <Card>
          <p className="muted">
            Темы доступны после завершения ML-анализа. См. PDF/XLSX-отчёт.
          </p>
        </Card>
      )}

      {tab === "reports" && (
        <Card>
          <Link to={`/campaigns/${campaignId}/reports`}>
            <Button>Перейти к отчётам</Button>
          </Link>
        </Card>
      )}
    </div>
  );
}
