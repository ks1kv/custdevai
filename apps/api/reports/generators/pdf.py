"""PDFReportGenerator — экстрактивный отчёт с трассируемыми цитатами.

Структура (FR-RPT-01):
  1. Титульный лист.
  2. Общая сводка (число сессий, статусы, дата анализа).
  3. Тональный анализ — круговая диаграмма + табличное распределение.
  4. Темы — горизонтальный bar chart + по каждой теме keywords +
     3 репрезентативные цитаты с псевдонимом R-NNNN (FR-RPT-05).
  5. Транскрипты — для каждой сессии: псевдоним + ответы по вопросам
     с метками тональности.

NFR-SEC-09 + §1.4.6 теор. главы: никакого LLM в формировании текста.
Все «инсайты» — прямые цитаты респондентов. Faithfulness = 1.0:
читатель может проследить каждый тезис до его источника.
"""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.api.db.models import SentimentLabel, SessionStatus
from apps.api.reports.charts import render_sentiment_pie, render_topics_hbar
from apps.api.reports.data_loader import CampaignReportContext

_FONT_DIR = Path(__file__).parent.parent / "fonts"
_FONT_REGULAR = "DejaVuSansBundled"
_FONT_BOLD = "DejaVuSansBundled-Bold"
_FONTS_REGISTERED = False


def _register_fonts() -> None:
    """Регистрация Cyrillic-шрифтов в ReportLab. Идемпотентно."""
    global _FONTS_REGISTERED  # noqa: PLW0603
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont(_FONT_REGULAR, str(_FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(_FONT_DIR / "DejaVuSans-Bold.ttf")))
    _FONTS_REGISTERED = True


_SENTIMENT_RU: dict[SentimentLabel, str] = {
    SentimentLabel.POSITIVE: "позитивная",
    SentimentLabel.NEUTRAL: "нейтральная",
    SentimentLabel.NEGATIVE: "негативная",
    SentimentLabel.LOW_CONFIDENCE: "низкая уверенность",
}

_STATUS_RU: dict[SessionStatus, str] = {
    SessionStatus.ACTIVE: "активная",
    SessionStatus.COMPLETED: "завершена",
    SessionStatus.INTERRUPTED: "прервана",
}


class PDFReportGenerator:
    """Сборщик PDF-отчёта по `CampaignReportContext`."""

    def __init__(self, ctx: CampaignReportContext) -> None:
        self._ctx = ctx
        _register_fonts()
        styles = getSampleStyleSheet()
        # Переопределяем все стили на DejaVu Sans (FR-RPT-02 кириллица).
        for s in styles.byName.values():
            if hasattr(s, "fontName"):
                s.fontName = _FONT_REGULAR
        self._styles = {
            "title": ParagraphStyle(
                "Title",
                parent=styles["Title"],
                fontName=_FONT_BOLD,
                fontSize=22,
                leading=26,
                alignment=1,
            ),
            "h1": ParagraphStyle(
                "H1",
                parent=styles["Heading1"],
                fontName=_FONT_BOLD,
                fontSize=16,
                leading=20,
                spaceBefore=10,
                spaceAfter=8,
            ),
            "h2": ParagraphStyle(
                "H2",
                parent=styles["Heading2"],
                fontName=_FONT_BOLD,
                fontSize=13,
                leading=16,
                spaceBefore=8,
                spaceAfter=4,
            ),
            "body": ParagraphStyle(
                "Body",
                parent=styles["BodyText"],
                fontName=_FONT_REGULAR,
                fontSize=10,
                leading=14,
                spaceAfter=4,
            ),
            "quote": ParagraphStyle(
                "Quote",
                parent=styles["BodyText"],
                fontName=_FONT_REGULAR,
                fontSize=10,
                leading=14,
                leftIndent=10 * mm,
                textColor=colors.HexColor("#404040"),
                spaceAfter=2,
            ),
            "small": ParagraphStyle(
                "Small",
                parent=styles["BodyText"],
                fontName=_FONT_REGULAR,
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#606060"),
            ),
        }

    def render(self) -> bytes:
        """Сгенерировать PDF и вернуть его байты."""
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            title=f"Отчёт по кампании «{self._ctx.campaign_title}»",
        )
        story: list = []
        self._cover(story)
        story.append(PageBreak())
        self._summary(story)
        self._sentiment_section(story)
        self._topics_section(story)
        story.append(PageBreak())
        self._transcripts_section(story)
        doc.build(story)
        return buf.getvalue()

    # ----- Sections --------------------------------------------------------

    def _cover(self, story: list) -> None:
        story.append(Spacer(1, 40 * mm))
        story.append(
            Paragraph(
                f"Отчёт по кампании<br/>«{self._ctx.campaign_title}»",
                self._styles["title"],
            )
        )
        story.append(Spacer(1, 16 * mm))
        meta = [
            f"<b>Сценарий:</b> {self._ctx.script_title}",
            f"<b>Дата генерации отчёта:</b> {self._ctx.generated_at:%Y-%m-%d %H:%M}",
            f"<b>Сессий всего:</b> {len(self._ctx.sessions)}",
            f"<b>Тем извлечено:</b> {sum(1 for t in self._ctx.topics if not t.is_noise)}",
        ]
        for line in meta:
            story.append(Paragraph(line, self._styles["body"]))

    def _summary(self, story: list) -> None:
        story.append(Paragraph("Общая сводка", self._styles["h1"]))
        completed = sum(
            1 for s in self._ctx.sessions if s.status == SessionStatus.COMPLETED
        )
        interrupted = sum(
            1 for s in self._ctx.sessions if s.status == SessionStatus.INTERRUPTED
        )
        active = sum(
            1 for s in self._ctx.sessions if s.status == SessionStatus.ACTIVE
        )

        rows = [
            ["Всего сессий", str(len(self._ctx.sessions))],
            ["Завершено", str(completed)],
            ["Прервано", str(interrupted)],
            ["Активных на момент отчёта", str(active)],
            ["Целевое число тем", str(self._ctx.target_topic_count)],
        ]
        if self._ctx.completed_at:
            rows.append(
                ["Дата завершения кампании", self._ctx.completed_at.strftime("%Y-%m-%d %H:%M")]
            )
        table = Table(rows, colWidths=[80 * mm, 80 * mm])
        table.setStyle(self._kv_table_style())
        story.append(table)
        story.append(Spacer(1, 8 * mm))

    def _sentiment_section(self, story: list) -> None:
        story.append(Paragraph("Анализ тональности", self._styles["h1"]))
        if not self._ctx.sentiment_distribution:
            story.append(
                Paragraph("Тональный анализ не проводился.", self._styles["body"])
            )
            return
        png = render_sentiment_pie(self._ctx.sentiment_distribution)
        story.append(Image(io.BytesIO(png), width=140 * mm, height=90 * mm))
        story.append(Spacer(1, 4 * mm))

        rows = [["Категория", "Число ответов"]]
        total = sum(self._ctx.sentiment_distribution.values())
        for label, count in self._ctx.sentiment_distribution.items():
            pct = (count / total * 100) if total else 0
            rows.append(
                [
                    _SENTIMENT_RU.get(label, label.value),
                    f"{count} ({pct:.0f}%)",
                ]
            )
        table = Table(rows, colWidths=[80 * mm, 80 * mm])
        table.setStyle(self._kv_table_style(header_row=True))
        story.append(table)

    def _topics_section(self, story: list) -> None:
        story.append(Paragraph("Ключевые темы", self._styles["h1"]))
        non_noise = [t for t in self._ctx.topics if not t.is_noise]
        if not non_noise:
            story.append(
                Paragraph("Темы не выявлены.", self._styles["body"])
            )
            return
        png = render_topics_hbar(self._ctx.topics)
        story.append(Image(io.BytesIO(png), width=160 * mm, height=110 * mm))
        story.append(Spacer(1, 4 * mm))

        for idx, topic in enumerate(non_noise, start=1):
            heading = topic.label or " / ".join(topic.keywords[:3]) or f"Тема {idx}"
            story.append(Paragraph(f"{idx}. {heading}", self._styles["h2"]))
            keywords_line = ", ".join(topic.keywords[:10]) or "—"
            story.append(
                Paragraph(
                    f"<b>Ключевые слова:</b> {keywords_line}",
                    self._styles["body"],
                )
            )
            story.append(
                Paragraph(
                    f"<b>Частота:</b> {topic.frequency_count} ответов",
                    self._styles["body"],
                )
            )
            if topic.quotes:
                story.append(
                    Paragraph("<b>Репрезентативные цитаты:</b>", self._styles["body"])
                )
                for pseudonym, quote in topic.quotes:
                    safe_quote = quote.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    story.append(
                        Paragraph(
                            f"«{safe_quote}» — <b>{pseudonym}</b>",
                            self._styles["quote"],
                        )
                    )
            story.append(Spacer(1, 4 * mm))

    def _transcripts_section(self, story: list) -> None:
        story.append(Paragraph("Транскрипты", self._styles["h1"]))
        if not self._ctx.sessions:
            story.append(Paragraph("Нет сессий.", self._styles["body"]))
            return

        answers_by_session: dict[int, list] = {s.session_id: [] for s in self._ctx.sessions}
        for ans in self._ctx.answers:
            answers_by_session.setdefault(ans.session_id, []).append(ans)

        for session in self._ctx.sessions:
            story.append(
                Paragraph(
                    f"{session.pseudonym} — {_STATUS_RU.get(session.status, session.status.value)}",
                    self._styles["h2"],
                )
            )
            session_answers = sorted(
                answers_by_session.get(session.session_id, []),
                key=lambda a: a.question_order,
            )
            if not session_answers:
                story.append(Paragraph("Нет ответов.", self._styles["small"]))
                story.append(Spacer(1, 3 * mm))
                continue
            for ans in session_answers:
                q_safe = ans.question_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                a_safe = ans.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                sentiment_suffix = ""
                if ans.sentiment_label is not None:
                    sentiment_suffix = (
                        f" <i>(тональность: "
                        f"{_SENTIMENT_RU.get(ans.sentiment_label, ans.sentiment_label.value)}"
                    )
                    if ans.sentiment_confidence is not None:
                        sentiment_suffix += f", уверенность {ans.sentiment_confidence:.2f}"
                    sentiment_suffix += ")</i>"
                story.append(
                    Paragraph(
                        f"<b>Вопрос {ans.question_order + 1}:</b> {q_safe}",
                        self._styles["body"],
                    )
                )
                story.append(
                    Paragraph(
                        f"<b>Ответ:</b> {a_safe}{sentiment_suffix}",
                        self._styles["body"],
                    )
                )
            story.append(Spacer(1, 4 * mm))

    # ----- Helpers ---------------------------------------------------------

    def _kv_table_style(self, *, header_row: bool = False) -> TableStyle:
        cmds: list = [
            ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1 if header_row else 0), (-1, -1), [colors.whitesmoke, colors.white]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if header_row:
            cmds.append(("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD))
            cmds.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")))
        return TableStyle(cmds)
