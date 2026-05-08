import { useState } from "react";
import { useForm } from "react-hook-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { createCampaign } from "@/api/campaigns";
import { listScripts } from "@/api/scripts";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Spinner } from "@/components/ui/Spinner";
import { t } from "@/lib/locales/ru";

interface FormValues {
  title: string;
  description: string;
  script_id: number;
  target_topic_count: number;
}

export function CampaignCreatePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: scripts, isLoading: scriptsLoading } = useQuery({
    queryKey: ["scripts"],
    queryFn: () => listScripts({ limit: 100 }),
  });

  const { register, handleSubmit, formState: { errors, isSubmitting } } =
    useForm<FormValues>({
      defaultValues: { target_topic_count: 10 },
    });

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      createCampaign({
        title: values.title,
        description: values.description || null,
        script_id: Number(values.script_id),
        target_topic_count: Number(values.target_topic_count),
      }),
    onSuccess: (c) => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      navigate(`/campaigns/${c.id}`);
    },
    onError: (err) => {
      setServerError(
        err instanceof ApiError ? err.problem.detail || err.problem.title : t.errors.generic,
      );
    },
  });

  if (scriptsLoading) return <Spinner />;

  return (
    <div>
      <div className="page-header">
        <h2>Новая кампания</h2>
      </div>
      <Card>
        <form onSubmit={handleSubmit((v) => mutation.mutate(v))} noValidate>
          <Input
            label="Название"
            error={errors.title?.message}
            {...register("title", { required: "Введите название" })}
          />
          <Textarea label="Описание" {...register("description")} />

          <div className="field">
            <label htmlFor="script_id">Сценарий</label>
            <select
              id="script_id"
              {...register("script_id", { required: true, valueAsNumber: true })}
              style={{
                border: "1px solid var(--c-border)",
                borderRadius: 6,
                padding: "8px 10px",
                background: "var(--c-surface)",
              }}
            >
              <option value="">— выберите сценарий —</option>
              {scripts?.items.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title} (вопросов: {s.questions.length})
                </option>
              ))}
            </select>
          </div>

          <Input
            label={t.campaign.targetTopicCount}
            type="number"
            min={3}
            max={20}
            {...register("target_topic_count", {
              valueAsNumber: true,
              min: { value: 3, message: "Не меньше 3" },
              max: { value: 20, message: "Не больше 20" },
            })}
            error={errors.target_topic_count?.message}
          />

          {serverError && <div className="danger">{serverError}</div>}

          <Button type="submit" loading={isSubmitting}>
            Создать
          </Button>
        </form>
      </Card>
    </div>
  );
}
