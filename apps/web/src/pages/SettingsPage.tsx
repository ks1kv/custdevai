/**
 * SettingsPage — профиль текущего пользователя.
 * Регистрация researcher_telegram_chat_id закрывает FR-BOT-09 — после
 * сохранения второй push «ML-анализ завершён» доставится непосредственно
 * исследователю.
 */

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useMutation } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { updateMe } from "@/api/users";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { t } from "@/lib/locales/ru";

interface FormValues {
  full_name: string;
  researcher_telegram_chat_id: string;
}

export function SettingsPage() {
  const { user, refresh } = useAuth();
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } =
    useForm<FormValues>({
      defaultValues: { full_name: "", researcher_telegram_chat_id: "" },
    });

  useEffect(() => {
    if (user) {
      reset({
        full_name: user.full_name ?? "",
        researcher_telegram_chat_id:
          user.researcher_telegram_chat_id != null
            ? String(user.researcher_telegram_chat_id)
            : "",
      });
    }
  }, [user, reset]);

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      const chatId = values.researcher_telegram_chat_id.trim();
      return updateMe({
        full_name: values.full_name.trim() || null,
        researcher_telegram_chat_id: chatId === "" ? null : Number(chatId),
      });
    },
    onSuccess: async () => {
      setError(null);
      setSaved(true);
      await refresh();
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (err) => {
      setSaved(false);
      setError(
        err instanceof ApiError ? err.problem.detail || err.problem.title : t.errors.generic,
      );
    },
  });

  if (!user) return <Spinner />;

  return (
    <div>
      <div className="page-header">
        <h2>{t.settings.title}</h2>
      </div>
      <Card style={{ maxWidth: 560 }}>
        <form onSubmit={handleSubmit((v) => mutation.mutate(v))} noValidate>
          <Input
            label={t.settings.email}
            value={user.email}
            disabled
            readOnly
          />
          <Input
            label={t.settings.fullName}
            error={errors.full_name?.message}
            {...register("full_name")}
          />
          <Input
            label={t.settings.telegramChatId}
            type="number"
            hint={t.settings.telegramHelp}
            error={errors.researcher_telegram_chat_id?.message}
            {...register("researcher_telegram_chat_id", {
              pattern: { value: /^-?\d*$/, message: "Только цифры" },
            })}
          />
          {saved && <div className="success">{t.settings.saved}</div>}
          {error && <div className="danger">{error}</div>}
          <Button type="submit" loading={isSubmitting}>
            {t.settings.save}
          </Button>
        </form>
      </Card>
    </div>
  );
}
