import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listScripts } from "@/api/scripts";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { t } from "@/lib/locales/ru";

export function ScriptsListPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["scripts"],
    queryFn: () => listScripts({ limit: 100 }),
  });

  return (
    <div>
      <div className="page-header">
        <h2>{t.nav.scripts}</h2>
        <Link to="/scripts/new">
          <Button>Новый сценарий</Button>
        </Link>
      </div>
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
