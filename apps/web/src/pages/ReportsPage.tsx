/**
 * ReportsPage — генерация и скачивание PDF/XLSX-отчётов кампании.
 * FR-WEB-10 / FR-RPT-01..08.
 *
 * Генерация недоступна, пока analysis_status != completed (FR-RPT-04).
 * SPA получает 409 — показываем понятный текст.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import {
  downloadReport,
  generateReport,
  getCampaign,
  listReports,
} from "@/api/campaigns";
import type { ReportFormat, ReportOut } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { t } from "@/lib/locales/ru";

export function ReportsPage() {
  const { id } = useParams();
  const campaignId = Number(id);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: campaign } = useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: () => getCampaign(campaignId),
  });
  const { data: reports, isLoading } = useQuery({
    queryKey: ["campaign", campaignId, "reports"],
    queryFn: () => listReports(campaignId),
  });

  const generate = useMutation({
    mutationFn: (format: ReportFormat) => generateReport(campaignId, format),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({
        queryKey: ["campaign", campaignId, "reports"],
      });
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.status === 409) setError(t.reports.notReady);
        else setError(err.problem.detail || err.problem.title);
      } else {
        setError(t.errors.generic);
      }
    },
  });

  const handleDownload = async (report: ReportOut) => {
    try {
      const blob = await downloadReport(campaignId, report.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `campaign-${campaignId}-report-${report.id}.${report.format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.problem.title : t.errors.generic);
    }
  };

  const ready = campaign?.analysis_status === "completed";

  return (
    <div>
      <div className="page-header">
        <h2>{t.reports.title}</h2>
      </div>

      <Card>
        {!ready && <p className="muted">{t.reports.notReady}</p>}
        <div className="toolbar">
          <Button
            disabled={!ready}
            loading={generate.isPending && generate.variables === "pdf"}
            onClick={() => generate.mutate("pdf")}
          >
            {t.reports.generatePdf}
          </Button>
          <Button
            variant="secondary"
            disabled={!ready}
            loading={generate.isPending && generate.variables === "xlsx"}
            onClick={() => generate.mutate("xlsx")}
          >
            {t.reports.generateXlsx}
          </Button>
        </div>
        {error && <div className="danger" style={{ marginTop: 12 }}>{error}</div>}
      </Card>

      <div style={{ marginTop: 16 }}>
        {isLoading && <Spinner />}
        {reports && reports.items.length === 0 && (
          <Card>
            <p className="muted">{t.reports.empty}</p>
          </Card>
        )}
        {reports && reports.items.length > 0 && (
          <Card>
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Формат</th>
                  <th>{t.reports.size}</th>
                  <th>{t.reports.generatedAt}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {reports.items.map((r) => (
                  <tr key={r.id}>
                    <td>{r.id}</td>
                    <td>{r.format.toUpperCase()}</td>
                    <td>{(r.file_size / 1024).toFixed(1)} КБ</td>
                    <td>{new Date(r.generated_at).toLocaleString("ru")}</td>
                    <td>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleDownload(r)}
                      >
                        {t.reports.download}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  );
}
