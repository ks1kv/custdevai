/**
 * Бейдж статуса кампании / анализа на русском.
 */

import type { CampaignAnalysisStatus, CampaignStatus } from "@/api/types";
import { t } from "@/lib/locales/ru";

export function CampaignStatusBadge({ status }: { status: CampaignStatus }) {
  return <span className={`badge ${status}`}>{t.campaign.status[status]}</span>;
}

export function AnalysisStatusBadge({ status }: { status: CampaignAnalysisStatus }) {
  return (
    <span className={`badge ${status}`}>{t.campaign.analysisStatus[status]}</span>
  );
}
