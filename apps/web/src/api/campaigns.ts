import { apiBlob, apiRequest } from "./client";
import type {
  CampaignAnalysisStatusOut,
  CampaignCreate,
  CampaignOut,
  CampaignSummaryOut,
  CampaignUpdate,
  Page,
  ReportFormat,
  ReportOut,
  SentimentLabel,
  TranscriptSession,
} from "./types";

export function listCampaigns(params: {
  status?: string;
  limit?: number;
  offset?: number;
}) {
  return apiRequest<Page<CampaignOut>>("/api/v1/campaigns", { query: params });
}

export function getCampaign(id: number) {
  return apiRequest<CampaignOut>(`/api/v1/campaigns/${id}`);
}

export function createCampaign(payload: CampaignCreate) {
  return apiRequest<CampaignOut>("/api/v1/campaigns", { method: "POST", body: payload });
}

export function updateCampaign(id: number, payload: CampaignUpdate) {
  return apiRequest<CampaignOut>(`/api/v1/campaigns/${id}`, {
    method: "PATCH",
    body: payload,
  });
}

export function deleteCampaign(id: number) {
  return apiRequest<void>(`/api/v1/campaigns/${id}`, { method: "DELETE" });
}

export function getAnalysisStatus(id: number) {
  return apiRequest<CampaignAnalysisStatusOut>(
    `/api/v1/campaigns/${id}/analysis-status`,
  );
}

export function getCampaignSummary(id: number) {
  return apiRequest<CampaignSummaryOut>(`/api/v1/campaigns/${id}/summary`);
}

export function startAnalysis(id: number) {
  return apiRequest<CampaignAnalysisStatusOut>(
    `/api/v1/campaigns/${id}/analyze`,
    { method: "POST" },
  );
}

export function listReports(campaignId: number) {
  return apiRequest<Page<ReportOut>>(
    `/api/v1/campaigns/${campaignId}/reports`,
    { query: { limit: 100 } },
  );
}

export function generateReport(campaignId: number, format: ReportFormat) {
  return apiRequest<ReportOut>(
    `/api/v1/campaigns/${campaignId}/reports/generate`,
    { method: "POST", query: { format } },
  );
}

export function downloadReport(campaignId: number, reportId: number) {
  return apiBlob(
    `/api/v1/campaigns/${campaignId}/reports/${reportId}/download`,
  );
}

export function listTranscripts(
  campaignId: number,
  params: {
    q?: string;
    sentiment?: SentimentLabel;
    limit?: number;
    offset?: number;
  } = {},
) {
  return apiRequest<Page<TranscriptSession>>(
    `/api/v1/campaigns/${campaignId}/transcripts`,
    { query: params },
  );
}
