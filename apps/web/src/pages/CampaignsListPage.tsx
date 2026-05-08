import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listCampaigns } from "@/api/campaigns";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { CampaignStatusBadge } from "@/components/StatusBadge";
import { t } from "@/lib/locales/ru";

export function CampaignsListPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["campaigns", "active"],
    queryFn: () => listCampaigns({ limit: 100 }),
    refetchInterval: 10_000,
  });

  return (
    <div>
      <div className="page-header">
        <h2>{t.nav.campaigns}</h2>
        <Link to="/campaigns/new">
          <Button>{t.dashboard.create}</Button>
        </Link>
      </div>
      {isLoading && <Spinner />}
      {data && (
        <Card>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Название</th>
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
                    <CampaignStatusBadge status={c.status} />
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
