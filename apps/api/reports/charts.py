"""matplotlib-чарты для отчётов: sentiment pie + topics hbar (FR-RPT-04).

`matplotlib.use("Agg")` — headless backend без GUI. Шрифт DejaVu Sans
подгружается из `apps/api/reports/fonts/`, чтобы кириллица отображалась
корректно (FR-RPT-02 spirit для встраиваемых растров).

Все функции возвращают `bytes` (PNG) — embedabble в PDF (ReportLab Image)
и XLSX (openpyxl Image).
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path

import matplotlib

# Headless backend нужно установить ДО первого импорта pyplot —
# иначе matplotlib инициализирует Tk/Qt и упадёт без $DISPLAY.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager

from apps.api.db.models import SentimentLabel
from apps.api.reports.data_loader import TopicView

_FONT_DIR = Path(__file__).parent / "fonts"
_REGULAR = _FONT_DIR / "DejaVuSans.ttf"
_BOLD = _FONT_DIR / "DejaVuSans-Bold.ttf"

# Регистрация шрифтов один раз при импорте модуля.
if _REGULAR.exists():
    font_manager.fontManager.addfont(str(_REGULAR))
if _BOLD.exists():
    font_manager.fontManager.addfont(str(_BOLD))
matplotlib.rcParams["font.family"] = "DejaVu Sans"

# Цвета совпадают с UI (Recharts будет использовать те же hex-коды).
_SENTIMENT_COLORS: dict[SentimentLabel, str] = {
    SentimentLabel.POSITIVE: "#22c55e",
    SentimentLabel.NEUTRAL: "#a3a3a3",
    SentimentLabel.NEGATIVE: "#ef4444",
    SentimentLabel.LOW_CONFIDENCE: "#f59e0b",
}
_SENTIMENT_LABELS_RU: dict[SentimentLabel, str] = {
    SentimentLabel.POSITIVE: "Позитивная",
    SentimentLabel.NEUTRAL: "Нейтральная",
    SentimentLabel.NEGATIVE: "Негативная",
    SentimentLabel.LOW_CONFIDENCE: "Низкая уверенность",
}


def render_sentiment_pie(distribution: dict[SentimentLabel, int]) -> bytes:
    """Круговая диаграмма распределения тональностей (FR-RPT-04)."""
    fig, ax = plt.subplots(figsize=(6, 4), dpi=120)

    if not distribution or sum(distribution.values()) == 0:
        ax.text(
            0.5,
            0.5,
            "Нет данных для отображения",
            ha="center",
            va="center",
            fontsize=14,
        )
        ax.axis("off")
    else:
        labels: list[str] = []
        sizes: list[int] = []
        colors: list[str] = []
        for sent_label, count in distribution.items():
            if count <= 0:
                continue
            labels.append(_SENTIMENT_LABELS_RU.get(sent_label, sent_label.value))
            sizes.append(count)
            colors.append(_SENTIMENT_COLORS.get(sent_label, "#cccccc"))
        ax.pie(
            sizes,
            labels=labels,
            colors=colors,
            autopct="%1.0f%%",
            startangle=90,
            textprops={"fontsize": 11},
        )
        ax.set_title("Распределение тональности ответов", fontsize=13)
    ax.axis("equal")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def render_topics_hbar(topics: Sequence[TopicView], *, max_topics: int = 12) -> bytes:
    """Горизонтальный bar chart частот тем (FR-RPT-04, FR-WEB-07).

    Шумовая тема (`is_noise=True`) исключается из визуализации
    (FR-TOP-06: «не учитываются в основной статистике»).
    """
    fig, ax = plt.subplots(figsize=(7, 5), dpi=120)
    visible = [t for t in topics if not t.is_noise][:max_topics]

    if not visible:
        ax.text(0.5, 0.5, "Темы не выявлены", ha="center", va="center", fontsize=14)
        ax.axis("off")
    else:
        # Снизу вверх — самая частая тема сверху.
        visible_sorted = sorted(visible, key=lambda t: t.frequency_count)
        labels = [
            t.label or " / ".join(t.keywords[:3]) or f"Тема {t.topic_id_in_model}"
            for t in visible_sorted
        ]
        values = [t.frequency_count for t in visible_sorted]
        ax.barh(labels, values, color="#2563eb")
        ax.set_xlabel("Число ответов")
        ax.set_title("Частота тем", fontsize=13)
        ax.tick_params(axis="y", labelsize=10)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
