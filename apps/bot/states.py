"""FSM-состояния диалога с респондентом (FR-BOT-01, 02, 05, 06, 07, 08).

Граф:
    AWAITING_CONSENT  ──(callback_data=consent:yes)──▶  IN_INTERVIEW
                      ──(/stop)──▶                      INTERRUPTED
    IN_INTERVIEW      ──(текстовый ответ ≤4096)──▶     IN_INTERVIEW (next q)
                                                       или COMPLETED (last q)
                      ──(текст или несколько сообщений)─▶ IN_INTERVIEW_LONG_ANSWER
                      ──(/stop)──▶                      INTERRUPTED
    IN_INTERVIEW_LONG_ANSWER ──(callback_data=long:done)─▶ IN_INTERVIEW (склейка→accept)
                              ──(ещё текст)──▶          IN_INTERVIEW_LONG_ANSWER
                              ──(/stop)──▶              INTERRUPTED

COMPLETED и INTERRUPTED — терминальные, FSM-state очищается. Повторный
/start от того же telegram_id с тем же campaign_id возвращает
информационное сообщение «Вы уже прошли это интервью».
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class InterviewState(StatesGroup):
    AWAITING_CONSENT = State()
    IN_INTERVIEW = State()
    IN_INTERVIEW_LONG_ANSWER = State()


# FSM data keys (хранятся в Redis под ключом aiogram-storage).
DATA_SESSION_ID = "session_id"
DATA_CAMPAIGN_ID = "campaign_id"
DATA_CURRENT_QUESTION_ID = "current_question_id"
DATA_PENDING_CHUNKS = "pending_chunks"
DATA_CONSENT_VERSION = "consent_version"
