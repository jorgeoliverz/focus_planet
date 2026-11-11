import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import errors

from focus_planet.coach import CoachError, get_weekly_coaching

CASES = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))


class FakeClient:
    """Cliente falso: nunca llama a la API real."""

    def __init__(self, case):
        self.models = self
        self.case = case

    def generate_content(self, **kwargs):
        if "api_error_code" in self.case:
            code = self.case["api_error_code"]
            raise errors.APIError(code, {"error": {"code": code, "message": "fake", "status": "FAKE"}})
        text = self.case.get("model_text") or json.dumps(self.case["model_output"])
        return SimpleNamespace(text=text)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "modelo-de-prueba")
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_caso(case):
    exp = case["expected"]
    client = FakeClient(case)
    if exp["ok"]:
        result = get_weekly_coaching(case["stats"], client=client)
        assert result.mood.value == exp["mood"]
        if exp.get("achievements_empty"):
            assert result.achievements == []
    else:
        with pytest.raises(CoachError) as exc:
            get_weekly_coaching(case["stats"], client=client)
        assert exc.value.code == exp["error_code"]
        assert exc.value.user_message


def _api_error(code):
    return errors.APIError(code, {"error": {"code": code, "message": "fake", "status": "FAKE"}})


class FlakyClient:
    def __init__(self, failures, code):
        self.models = self
        self.failures, self.code, self.calls = failures, code, 0

    def generate_content(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise _api_error(self.code)
        return SimpleNamespace(text=json.dumps(CASES[0]["model_output"]))


def test_reintenta_503_y_se_recupera(monkeypatch):
    monkeypatch.setattr("focus_planet.coach.time.sleep", lambda s: None)
    client = FlakyClient(failures=2, code=503)
    assert get_weekly_coaching(CASES[0]["stats"], client=client).mood.value == "celebrating"
    assert client.calls == 3


def test_503_persistente_falla_tras_3_intentos(monkeypatch):
    monkeypatch.setattr("focus_planet.coach.time.sleep", lambda s: None)
    client = FlakyClient(failures=99, code=503)
    with pytest.raises(CoachError) as exc:
        get_weekly_coaching(CASES[0]["stats"], client=client)
    assert exc.value.code == "api_error" and client.calls == 3


def test_429_no_se_reintenta(monkeypatch):
    monkeypatch.setattr("focus_planet.coach.time.sleep", lambda s: None)
    client = FlakyClient(failures=99, code=429)
    with pytest.raises(CoachError) as exc:
        get_weekly_coaching(CASES[0]["stats"], client=client)
    assert exc.value.code == "rate_limit" and client.calls == 1
