import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { deleteCampaign, listCampaigns } from "@/api/campaigns";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { CampaignStatusBadge } from "@/components/StatusBadge";
import { t } from "@/lib/locales/ru";

export function CampaignsListPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["campaigns", "active"],
    queryFn: () => listCampaigns({ limit: 100 }),
    refetchInterval: 10_000,
  });
  const [error, setError] = useState<string | null>(null);

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteCampaign(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
    onError: (err) => {
      setError(
        err instanceof ApiError ? err.problem.detail || err.problem.title : t.errors.generic,
      );
    },
  });

  const handleDelete = (id: number, title: string) => {
    if (
      !window.confirm(
        `Удалить кампанию «${title}» вместе со всеми её данными (сессии, ответы, отчёты)? ` +
          `Действие необратимо.`,
      )
    )
      return;
    setError(null);
    deleteMutation.mutate(id);
  };

  return (
    <div>
      <div className="page-header">
        <h2>{t.nav.campaigns}</h2>
        <Link to="/campaigns/new">
          <Button>{t.dashboard.create}</Button>
        </Link>
      </div>
      {error && (
        <div className="danger" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}
      {isLoading && <Spinner />}
      {data && (
        <Card>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Название</th>
                <th>Статус</th>
                <th aria-label="Действия" />
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
                  <td style={{ textAlign: "right" }}>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(c.id, c.title)}
                      disabled={deleteMutation.isPending}
                    >
                      {t.common.delete}
                    </Button>
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
