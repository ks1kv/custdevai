"""Безвозвратное удаление данных субъекта (FR-DB-07, № 152-ФЗ).

Реализует операцию полного физического удаления записей конкретного
респондента по его запросу:
- answers и sentiment_results (CASCADE через answers→sentiment_results),
- session_topics,
- consents,
- interview_sessions.

Удаление НЕ затрагивает другие сессии/кампании и НЕ переписывает
агрегаты тем/тональности (`topics` агрегируются на уровне кампании
и не привязаны к telegram_id_hash).

После выполнения в audit_log пишется запись DATA_DELETION_REQUESTED
с perform_counts по таблицам — этот журнал сам по себе не содержит
ПДн (только хеши).

Возвращается DataDeletionReceipt — JSON-акт удаления, который вызывающий
(админ или сам субъект) может сохранить для соответствия требованиям
№ 152-ФЗ статьи 14 части 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models import (
    Answer,
    AuditAction,
    Consent,
    InterviewSession,
    SentimentResult,
    SessionTopic,
)
from apps.api.errors import NotFound
from apps.api.services.audit import AuditService


@dataclass(frozen=True)
class DataDeletionReceipt:
    """Акт удаления для возврата субъекту / админу."""

    performed_at: datetime
    telegram_id_hash_hex: str
    affected: dict[str, int]
    audit_id: int | None


class DataDeletionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditService(session)

    async def delete_by_telegram_hash(
        self,
        telegram_id_hash: bytes,
        *,
        actor_user_id: int | None,
        ip_address: str | None = None,
    ) -> DataDeletionReceipt:
        """Удалить все данные субъекта по его telegram_id_hash.

        Args:
            telegram_id_hash: SHA-256 хеш Telegram ID с per-campaign солью
                (FR-DB-03). Один и тот же субъект мог пройти несколько
                кампаний — у каждой свой хеш. Удаляем все сессии с этим хешем.
            actor_user_id: кто выполнил удаление (admin / системный токен).
            ip_address: IP клиента, для записи в audit_log.

        Raises:
            NotFound: если не найдено ни одной сессии с таким хешем.
        """
        if len(telegram_id_hash) != 32:
            raise ValueError("telegram_id_hash должен быть 32 байта (SHA-256)")

        # 1. Найти все session_id субъекта.
        session_ids = list(
            (
                await self._session.execute(
                    select(InterviewSession.id).where(
                        InterviewSession.telegram_id_hash == telegram_id_hash
                    )
                )
            ).scalars()
        )
        if not session_ids:
            raise NotFound("Данные субъекта не найдены.")

        # 2. Найти все answer_id перед каскадным удалением (для аналитики и
        #    для гарантированной очистки sentiment_results, если CASCADE
        #    не настроен на уровне БД).
        answer_ids = list(
            (
                await self._session.execute(
                    select(Answer.id).where(Answer.session_id.in_(session_ids))
                )
            ).scalars()
        )

        affected: dict[str, int] = {}

        # 3. Удаляем по dependency-order: sentiment_results → session_topics
        #    → answers → consents → interview_sessions.
        if answer_ids:
            res = await self._session.execute(
                delete(SentimentResult).where(SentimentResult.answer_id.in_(answer_ids))
            )
            affected["sentiment_results"] = res.rowcount or 0

        res = await self._session.execute(
            delete(SessionTopic).where(SessionTopic.session_id.in_(session_ids))
        )
        affected["session_topics"] = res.rowcount or 0

        res = await self._session.execute(delete(Answer).where(Answer.session_id.in_(session_ids)))
        affected["answers"] = res.rowcount or 0

        res = await self._session.execute(
            delete(Consent).where(Consent.session_id.in_(session_ids))
        )
        affected["consents"] = res.rowcount or 0

        res = await self._session.execute(
            delete(InterviewSession).where(InterviewSession.id.in_(session_ids))
        )
        affected["interview_sessions"] = res.rowcount or 0

        # 4. Записываем acт удаления в audit_log. AuditLog хеш НЕ хранит —
        #    только counts и list session_ids (которые сами по себе ПДн
        #    не являются после удаления связанных строк).
        details = {
            "session_ids": session_ids,
            "answer_ids": answer_ids,
            "affected": affected,
            "legal_basis": "ФЗ-152 ст. 14 ч. 1 (право субъекта на удаление)",
        }
        audit_entry = await self._audit.record(
            AuditAction.DATA_DELETION_REQUESTED,
            user_id=actor_user_id,
            ip_address=ip_address,
            details=details,
        )

        await self._session.commit()

        return DataDeletionReceipt(
            performed_at=datetime.now(tz=timezone.utc),
            telegram_id_hash_hex=telegram_id_hash.hex(),
            affected=affected,
            audit_id=audit_entry.id,
        )
