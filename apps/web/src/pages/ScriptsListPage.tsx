import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { deleteScript, listScripts } from "@/api/scripts";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { t } from "@/lib/locales/ru";

export function ScriptsListPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["scripts"],
    queryFn: () => listScripts({ limit: 100 }),
  });
  const [error, setError] = useState<string | null>(null);

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteScript(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scripts"] });
    },
    onError: (err) => {
      setError(
        err instanceof ApiError ? err.problem.detail || err.problem.title : t.errors.generic,
      );
    },
  });

  const handleDelete = (id: number, title: string) => {
    if (!window.confirm(`Удалить сценарий «${title}»? Действие необратимо.`)) return;
    setError(null);
    deleteMutation.mutate(id);
  };

  return (
    <div>
      <div className="page-header">
        <h2>{t.nav.scripts}</h2>
        <Link to="/scripts/new">
          <Button>Новый сценарий</Button>
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
          {data.items.length === 0 ? (
            <p className="muted">Сценариев пока нет.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Название</th>
                  <th>Вопросов</th>
                  <th aria-label="Действия" />
                </tr>
              </thead>
              <tbody>
                {data.items.map((s) => (
                  <tr key={s.id}>
                    <td>{s.id}</td>
                    <td>
                      <Link to={`/scripts/${s.id}`}>{s.title}</Link>
                    </td>
                    <td>{s.questions.length}</td>
                    <td style={{ textAlign: "right" }}>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(s.id, s.title)}
                        disabled={deleteMutation.isPending}
                      >
                        {t.common.delete}
                      </Button>
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
