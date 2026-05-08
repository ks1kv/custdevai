/**
 * DashboardPage — список кампаний с real-time-обновлением статусов
 * (FR-WEB-04: refetchInterval = 10 сек).
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listCampaigns } from "@/api/campaigns";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import {
  AnalysisStatusBadge,
  CampaignStatusBadge,
} from "@/components/StatusBadge";
import { t } from "@/lib/locales/ru";

export function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["campaigns", "all"],
    queryFn: () => listCampaigns({ limit: 100 }),
    refetchInterval: 10_000,
  });

  return (
    <div>
      <div className="page-header">
        <h2>{t.dashboard.title}</h2>
        <div className="toolbar">
          <Link to="/wizard">
            <Button variant="secondary">{t.dashboard.wizard}</Button>
          </Link>
          <Link to="/campaigns/new">
            <Button>{t.dashboard.create}</Button>
          </Link>
        </div>
      </div>

      {isLoading && <Spinner />}
      {error && <div className="danger">{t.errors.network}</div>}

      {data && data.items.length === 0 && (
        <Card>
          <p className="muted">{t.dashboard.empty}</p>
        </Card>
      )}

      {data && data.items.length > 0 && (
        <Card>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Название</th>
                <th>Статус</th>
                <th>Анализ</th>
                <th>Тем (цель)</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td>
                    <Link to={`/campaigns/${c.id}`}>{c.title}</Link>
                  </td>
                  <td>
                    <CampaignStatusBadge status={c.status} />
                  </td>
                  <td>
                    <AnalysisStatusBadge status={c.analysis_status} />
                  </td>
                  <td>{c.target_topic_count}</td>
                  <td>
                    <Link to={`/campaigns/${c.id}/reports`}>
                      <Button variant="ghost" size="sm">
                        {t.campaign.tabs.reports}
                      </Button>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
