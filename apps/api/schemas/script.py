"""DTO для сценариев и вопросов."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class QuestionIn(BaseModel):
    text: str = Field(min_length=1, max_length=2048)
    order_index: int = Field(ge=0, le=10000)
    is_required: bool = True
    hint_text: str | None = Field(default=None, max_length=2048)


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    script_id: int
    text: str
    order_index: int
    is_required: bool
    hint_text: str | None


class ScriptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    questions: list[QuestionIn] = Field(default_factory=list)


class ScriptUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    # Если передан — полностью заменяет набор вопросов сценария. Запрос
    # отклоняется (409), если хоть один существующий вопрос уже имеет
    # ответы (FK answers.question_id ON DELETE RESTRICT).
    questions: list[QuestionIn] | None = Field(default=None)


class ScriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    created_by_user_id: int | None
    questions: list[QuestionOut] = Field(default_factory=list)


class QuestionUpsert(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=2048)
    order_index: int | None = Field(default=None, ge=0, le=10000)
    is_required: bool | None = None
    hint_text: str | None = Field(default=None, max_length=2048)
