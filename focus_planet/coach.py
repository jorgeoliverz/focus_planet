"""Coach semanal con Gemini: habla con el usuario sobre sus logros y cómo mejorar."""
from __future__ import annotations

import json
import os
import time
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field, ValidationError

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "weekly_coach.md"

RETRY_CODES = {500, 503, 504}
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2  # se duplica en cada reintento

MSG_RATE_LIMIT = "Tu compañero está agotado ahora mismo (demasiadas peticiones). Inténtalo de nuevo en un minuto."
MSG_INVALID = "Tu compañero no consiguió responder bien. Inténtalo de nuevo más tarde."
MSG_GENERIC = "No se pudo contactar con tu compañero. Inténtalo de nuevo más tarde."
MSG_CONFIG = "El coach no está configurado (falta GEMINI_API_KEY o GEMINI_MODEL en .env)."


class Mood(str, Enum):
    celebrating = "celebrating"
    encouraging = "encouraging"
    supportive = "supportive"


class WeeklyCoaching(BaseModel):
    summary: str = Field(min_length=1, max_length=400)
    achievements: list[str] = Field(default_factory=list, max_length=4)
    improvements: list[str] = Field(min_length=1, max_length=3)
    next_goal_minutes: int = Field(ge=0, le=1440)
    mood: Mood


class CoachError(Exception):
    """Error pensado para mostrarse al usuario (`user_message`)."""

    def __init__(self, user_message: str, *, code: str):
        super().__init__(user_message)
        self.user_message = user_message
        self.code = code  # "rate_limit" | "invalid_response" | "api_error" | "config"


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def get_weekly_coaching(stats: dict, client: genai.Client | None = None) -> WeeklyCoaching:
    """Pide a Gemini feedback semanal. Lanza CoachError si algo falla."""
    load_dotenv()
    model = os.getenv("GEMINI_MODEL")
    if client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or not model:
            raise CoachError(MSG_CONFIG, code="config")
        client = genai.Client(api_key=api_key)
    elif not model:
        raise CoachError(MSG_CONFIG, code="config")

    config = types.GenerateContentConfig(
        system_instruction=_load_prompt(),
        response_mime_type="application/json",
        response_schema=WeeklyCoaching,
    )
    response = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=model, contents=json.dumps(stats, ensure_ascii=False), config=config
            )
            break
        except errors.APIError as e:
            if e.code == 429:  # no se reintenta: insistir empeora el límite
                raise CoachError(MSG_RATE_LIMIT, code="rate_limit") from e
            if e.code in RETRY_CODES and attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS * 2 ** (attempt - 1))
                continue
            raise CoachError(MSG_GENERIC, code="api_error") from e
        except Exception as e:  # red, timeouts, etc.
            raise CoachError(MSG_GENERIC, code="api_error") from e

    try:
        return WeeklyCoaching.model_validate_json(response.text or "")
    except (ValidationError, ValueError) as e:
        raise CoachError(MSG_INVALID, code="invalid_response") from e
