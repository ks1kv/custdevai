/**
 * ScriptBuilderPage — создание/редактирование сценария.
 * FR-WEB-01: добавление/удаление/реордеринг вопросов.
 * FR-WEB-02: редактирование заблокировано, если есть кампания в статусе running
 *           (API возвращает 409 — показываем текст ошибки на русском).
 */

import { useEffect, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { createScript, getScript, updateScript } from "@/api/scripts";
import type { ScriptCreate } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Spinner } from "@/components/ui/Spinner";
import { t } from "@/lib/locales/ru";

interface FormValues {
  title: string;
  description: string;
  questions: Array<{
    text: string;
    order_index: number;
    is_required: boolean;
    hint_text: string;
  }>;
}

export function ScriptBuilderPage() {
  const { id } = useParams();
  const isNew = !id;
  const scriptId = id ? Number(id) : null;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: existing, isLoading } = useQuery({
    queryKey: ["script", scriptId],
    queryFn: () => getScript(scriptId!),
    enabled: scriptId !== null,
  });

  const { register, control, handleSubmit, reset, formState: { isSubmitting, errors } } =
    useForm<FormValues>({
      defaultValues: {
        title: "",
        description: "",
        questions: [{ text: "", order_index: 1, is_required: true, hint_text: "" }],
      },
    });
  const { fields, append, remove } = useFieldArray({ control, name: "questions" });

  useEffect(() => {
    if (existing) {
      reset({
        title: existing.title,
        description: existing.description ?? "",
        questions: existing.questions.map((q) => ({
          text: q.text,
          order_index: q.order_index,
          is_required: q.is_required,
          hint_text: q.hint_text ?? "",
        })),
      });
    }
  }, [existing, reset]);

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      const payload: ScriptCreate = {
        title: values.title,
        description: values.description || null,
        questions: values.questions.map((q, idx) => ({
          text: q.text,
          order_index: idx + 1,
          is_required: q.is_required,
          hint_text: q.hint_text || null,
        })),
      };
      if (scriptId) return updateScript(scriptId, payload);
      return createScript(payload);
    },
    onSuccess: (s) => {
      queryClient.invalidateQueries({ queryKey: ["scripts"] });
      queryClient.invalidateQueries({ queryKey: ["script", s.id] });
      navigate("/scripts");
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setServerError(err.problem.detail || err.problem.title);
      } else {
        setServerError(t.errors.generic);
      }
    },
  });

  if (isLoading) return <Spinner />;

  return (
    <div>
      <div className="page-header">
        <h2>{isNew ? "Новый сценарий" : `Сценарий #${scriptId}`}</h2>
      </div>
      <Card>
        <form onSubmit={handleSubmit((v) => mutation.mutate(v))} noValidate>
          <Input
            label="Название"
            error={errors.title?.message}
            {...register("title", { required: "Введите название" })}
          />
          <Textarea label="Описание" {...register("description")} />

          <h3 style={{ marginTop: 16 }}>Вопросы</h3>
          {fields.map((field, idx) => (
            <div
              key={field.id}
              style={{
                border: "1px solid var(--c-border)",
                borderRadius: 6,
                padding: 12,
                marginBottom: 8,
              }}
            >
              <div className="toolbar" style={{ marginBottom: 8 }}>
                <strong>#{idx + 1}</strong>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => remove(idx)}
                  disabled={fields.length === 1}
                >
                  {t.common.delete}
                </Button>
              </div>
              <Textarea
                label="Текст вопроса"
                rows={2}
                error={errors.questions?.[idx]?.text?.message}
                {...register(`questions.${idx}.text`, {
                  required: "Текст обязателен",
                })}
              />
              <Input
                label="Подсказка (необязательно)"
                {...register(`questions.${idx}.hint_text`)}
              />
              <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="checkbox"
                  {...register(`questions.${idx}.is_required`)}
                />
                Обязательный
              </label>
            </div>
          ))}
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              append({
                text: "",
                order_index: fields.length + 1,
                is_required: true,
                hint_text: "",
              })
            }
          >
            + Добавить вопрос
          </Button>

          {serverError && (
            <div className="danger" style={{ marginTop: 12 }}>
              {serverError}
            </div>
          )}

          <div style={{ marginTop: 16 }}>
            <Button type="submit" loading={isSubmitting}>
              {t.common.save}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
