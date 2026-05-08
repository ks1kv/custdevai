/**
 * LoginPage — форма входа с email/password.
 * При успехе SPA полагается на httpOnly cookies, выставленные API.
 */

import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { t } from "@/lib/locales/ru";

interface FormValues {
  email: string;
  password: string;
}

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>();

  if (user) return <Navigate to="/" replace />;

  const from = (location.state as { from?: Location })?.from?.pathname ?? "/";

  const onSubmit = async (values: FormValues) => {
    setServerError(null);
    try {
      await login(values.email, values.password);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429) setServerError(t.login.errorRateLimit);
        else if (err.status === 401) setServerError(t.login.errorCredentials);
        else setServerError(err.problem.detail || err.problem.title);
      } else {
        setServerError(t.errors.network);
      }
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--c-bg)",
      }}
    >
      <Card title={t.login.title} style={{ width: 380 }}>
        <p className="muted" style={{ marginTop: 0 }}>
          {t.app.subtitle}
        </p>
        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            label={t.login.email}
            error={errors.email?.message}
            {...register("email", {
              required: "Введите email",
              pattern: {
                value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                message: "Некорректный email",
              },
            })}
          />
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            label={t.login.password}
            error={errors.password?.message}
            {...register("password", { required: "Введите пароль" })}
          />
          {serverError && (
            <div
              role="alert"
              style={{
                background: "#fef2f2",
                border: "1px solid #fecaca",
                color: "#b91c1c",
                padding: "8px 10px",
                borderRadius: 6,
                marginBottom: 12,
                fontSize: 13,
              }}
            >
              {serverError}
            </div>
          )}
          <Button type="submit" loading={isSubmitting} style={{ width: "100%" }}>
            {t.login.submit}
          </Button>
        </form>
      </Card>
    </div>
  );
}
