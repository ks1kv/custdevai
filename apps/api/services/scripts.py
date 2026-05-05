"""Бизнес-логика сценариев и вопросов."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models import Question, Script
from apps.api.db.repositories.scripts import ScriptRepository
from apps.api.errors import Conflict, NotFound
from apps.api.schemas.script import QuestionIn, QuestionUpsert, ScriptCreate, ScriptUpdate


class ScriptService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ScriptRepository(session)

    async def create(self, payload: ScriptCreate, *, owner_id: int) -> Script:
        script = Script(
            title=payload.title,
            description=payload.description,
            created_by_user_id=owner_id,
        )
        self._session.add(script)
        await self._session.flush()
        for q in payload.questions:
            self._session.add(
                Question(
                    script_id=script.id,
                    text=q.text,
                    order_index=q.order_index,
                    is_required=q.is_required,
                    hint_text=q.hint_text,
                )
            )
        await self._session.commit()
        await self._session.refresh(script, attribute_names=["questions"])
        return script

    async def get(self, script_id: int, *, owner_id: int | None) -> Script:
        script = await self._repo.get(script_id)
        if script is None:
            raise NotFound("Сценарий не найден.")
        if owner_id is not None and script.created_by_user_id != owner_id:
            raise NotFound("Сценарий не найден.")
        return script

    async def list_(
        self, *, limit: int, offset: int, owner_id: int | None
    ) -> tuple[list[Script], int]:
        return await self._repo.list_paginated(limit=limit, offset=offset, owner_id=owner_id)

    async def update(
        self, script_id: int, payload: ScriptUpdate, *, owner_id: int | None
    ) -> Script:
        script = await self.get(script_id, owner_id=owner_id)
        if await self._repo.has_running_campaign(script_id):
            raise Conflict("Сценарий нельзя править, пока с ним связана активная кампания.")
        if payload.title is not None:
            script.title = payload.title
        if payload.description is not None:
            script.description = payload.description
        await self._session.commit()
        await self._session.refresh(script, attribute_names=["questions"])
        return script

    async def delete(self, script_id: int, *, owner_id: int | None) -> None:
        script = await self.get(script_id, owner_id=owner_id)
        if await self._repo.has_any_campaign(script_id):
            raise Conflict(
                "Сценарий не может быть удалён, пока с ним связаны кампании. "
                "Сначала удалите или перепривяжите кампании."
            )
        await self._repo.delete(script)
        await self._session.commit()

    async def add_question(
        self, script_id: int, payload: QuestionIn, *, owner_id: int | None
    ) -> Question:
        script = await self.get(script_id, owner_id=owner_id)
        question = Question(
            script_id=script.id,
            text=payload.text,
            order_index=payload.order_index,
            is_required=payload.is_required,
            hint_text=payload.hint_text,
        )
        self._session.add(question)
        await self._session.commit()
        return question

    async def update_question(
        self,
        script_id: int,
        question_id: int,
        payload: QuestionUpsert,
        *,
        owner_id: int | None,
    ) -> Question:
        await self.get(script_id, owner_id=owner_id)
        question = await self._repo.get_question(question_id)
        if question is None or question.script_id != script_id:
            raise NotFound("Вопрос не найден.")
        if payload.text is not None:
            question.text = payload.text
        if payload.order_index is not None:
            question.order_index = payload.order_index
        if payload.is_required is not None:
            question.is_required = payload.is_required
        if payload.hint_text is not None:
            question.hint_text = payload.hint_text
        await self._session.commit()
        return question

    async def delete_question(
        self, script_id: int, question_id: int, *, owner_id: int | None
    ) -> None:
        await self.get(script_id, owner_id=owner_id)
        question = await self._repo.get_question(question_id)
        if question is None or question.script_id != script_id:
            raise NotFound("Вопрос не найден.")
        await self._repo.delete_question(question)
        await self._session.commit()
