/**
 * ArchivePage — список завершённых кампаний (FR-WEB-09).
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listCampaigns } from "@/api/campaigns";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { CampaignStatusBadge } from "@/components/StatusBadge";
import { t } from "@/lib/locales/ru";

export function ArchivePage() {
  const { data, isLoading } = useQuery({
    queryKey: ["campaigns", "completed"],
    queryFn: () => listCampaigns({ status: "completed", limit: 100 }),
  });

  return (
    <div>
      <div className="page-header">
        <h2>{t.nav.archive}</h2>
      </div>
      {isLoading && <Spinner />}
      {data && (
        <Card>
          {data.items.length === 0 ? (
            <p className="muted">Завершённых кампаний пока нет.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Название</th>
                  <th>Завершена</th>
                  <th>Статус</th>
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
                      {c.completed_at
                        ? new Date(c.completed_at).toLocaleDateString("ru")
                        : "—"}
                    </td>
                    <td>
                      <CampaignStatusBadge status={c.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}
    </div>
  );
}
