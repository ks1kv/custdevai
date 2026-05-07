"""Unit-тесты FSM-состояний бота с MemoryStorage."""

from __future__ import annotations

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from apps.bot.states import (
    DATA_CAMPAIGN_ID,
    DATA_CURRENT_QUESTION_ID,
    DATA_PENDING_CHUNKS,
    DATA_SESSION_ID,
    InterviewState,
)


@pytest.fixture
def fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


@pytest.mark.asyncio
async def test_initial_state_is_none(fsm_context: FSMContext) -> None:
    assert await fsm_context.get_state() is None


@pytest.mark.asyncio
async def test_transitions_through_consent_to_interview(fsm_context: FSMContext) -> None:
    await fsm_context.set_state(InterviewState.AWAITING_CONSENT)
    assert await fsm_context.get_state() == InterviewState.AWAITING_CONSENT.state

    await fsm_context.set_state(InterviewState.IN_INTERVIEW)
    assert await fsm_context.get_state() == InterviewState.IN_INTERVIEW.state


@pytest.mark.asyncio
async def test_data_storage_round_trip(fsm_context: FSMContext) -> None:
    await fsm_context.set_data(
        {
            DATA_SESSION_ID: 42,
            DATA_CAMPAIGN_ID: 7,
            DATA_CURRENT_QUESTION_ID: 100,
            DATA_PENDING_CHUNKS: ["а", "б"],
        }
    )
    data = await fsm_context.get_data()
    assert data[DATA_SESSION_ID] == 42
    assert data[DATA_CAMPAIGN_ID] == 7
    assert data[DATA_PENDING_CHUNKS] == ["а", "б"]


@pytest.mark.asyncio
async def test_clear_resets_state_and_data(fsm_context: FSMContext) -> None:
    await fsm_context.set_state(InterviewState.IN_INTERVIEW)
    await fsm_context.set_data({DATA_SESSION_ID: 1})
    await fsm_context.clear()
    assert await fsm_context.get_state() is None
    assert await fsm_context.get_data() == {}


@pytest.mark.asyncio
async def test_long_answer_state_separate_from_in_interview(
    fsm_context: FSMContext,
) -> None:
    await fsm_context.set_state(InterviewState.IN_INTERVIEW)
    await fsm_context.set_state(InterviewState.IN_INTERVIEW_LONG_ANSWER)
    assert (
        await fsm_context.get_state() == InterviewState.IN_INTERVIEW_LONG_ANSWER.state
    )
