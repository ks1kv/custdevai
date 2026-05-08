/**
 * FirstCampaignWizard — мастер первой кампании (FR-WEB-11, NFR-USE-01).
 * Минимальный flow в Phase 4: четыре шага, где первые три — ссылки на
 * соответствующие страницы. Полная inline-анкета — Phase 5.
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { t } from "@/lib/locales/ru";

export function WizardPage() {
  const [step, setStep] = useState(0);
  const steps = [t.wizard.step1, t.wizard.step2, t.wizard.step3, t.wizard.step4];

  return (
    <div>
      <div className="page-header">
        <h2>{t.wizard.title}</h2>
      </div>

      <Card>
        <div className="toolbar" style={{ marginBottom: 16 }}>
          {steps.map((s, idx) => (
            <span
              key={idx}
              className={`badge ${idx === step ? "running" : "draft"}`}
              style={{ cursor: "pointer" }}
              onClick={() => setStep(idx)}
            >
              {idx + 1}. {s}
            </span>
          ))}
        </div>

        {step === 0 && (
          <>
            <p>
              Создайте сценарий с 5–10 открытыми вопросами по проблемам и потребностям
              целевой аудитории. Используйте формулировки без подсказок ответа.
            </p>
            <Link to="/scripts/new">
              <Button>Открыть редактор сценария</Button>
            </Link>
          </>
        )}

        {step === 1 && (
          <>
            <p>
              Перейдите в созданный сценарий и добавьте список вопросов по порядку.
              Можно отметить часть вопросов как необязательные.
            </p>
            <Link to="/scripts">
              <Button>К списку сценариев</Button>
            </Link>
          </>
        )}

        {step === 2 && (
          <>
            <p>
              Создайте кампанию, выбрав сценарий, и переведите её в статус «Активна».
              Бот выдаст ссылку-приглашение для распространения среди респондентов.
            </p>
            <Link to="/campaigns/new">
              <Button>Создать кампанию</Button>
            </Link>
          </>
        )}

        {step === 3 && (
          <>
            <p>
              Готово. Когда соберётся достаточно ответов, запустите ML-анализ во вкладке
              «Обзор» кампании, затем сгенерируйте PDF/XLSX отчёт.
            </p>
            <Link to="/">
              <Button>На дашборд</Button>
            </Link>
          </>
        )}

        <div className="toolbar" style={{ marginTop: 16, justifyContent: "space-between" }}>
          <Button
            variant="secondary"
            disabled={step === 0}
            onClick={() => setStep((s) => Math.max(0, s - 1))}
          >
            {t.wizard.back}
          </Button>
          <Button
            disabled={step === steps.length - 1}
            onClick={() => setStep((s) => Math.min(steps.length - 1, s + 1))}
          >
            {t.wizard.next}
          </Button>
        </div>
      </Card>
    </div>
  );
}
