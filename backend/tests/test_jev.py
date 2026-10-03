import pytest

from app.config import Settings
from app.demo import scenarios
from app.models.decisions import OverallQuality, PrimaryIssue, Severity
from app.services import jev as jev_module
from app.services.jev import DecisionService, JevError, _compact_state, parse_jev_response

VALID_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "primary_issue": {
            "type": "choice",
            "choice": "too_fast",
            "confidence": 0.91,
            "probabilities": {"too_fast": 0.82, "good": 0.11, "inconsistent": 0.07},
        },
        "severity": {
            "type": "score",
            "score": 1.4,
            "confidence": 0.7,
            "legend": {"0": "none", "1": "mild", "2": "moderate", "3": "major"},
            "probabilities": {"0": 0.0, "1": 0.6, "2": 0.4, "3": 0.0},
        },
        "coaching_priority": {"type": "choice", "choice": "tempo", "confidence": 0.8, "probabilities": {}},
        "should_speak": {"type": "noul", "noul": 0.93},
        "overall_quality": {
            "type": "score",
            "score": 1.2,
            "confidence": 0.6,
            "legend": {"0": "poor", "1": "fair", "2": "good", "3": "excellent"},
            "probabilities": {},
        },
    },
    "usage": {"input_tokens": 300, "output_tokens": 40},
}


def test_parse_valid_jev_response():
    metrics = scenarios.too_fast()
    decision = parse_jev_response(VALID_RESPONSE, metrics, "jev-latest")
    assert decision.primary_issue is PrimaryIssue.TOO_FAST
    assert decision.severity is Severity.MILD  # score 1.4 rounds to level 1
    assert decision.overall_quality is OverallQuality.FAIR  # score 1.2 rounds to level 1
    assert decision.should_speak is True
    assert decision.provider == "jev"
    assert decision.model_version == "jev-1.13.0"
    assert decision.alternatives["TOO_FAST"] == pytest.approx(0.82)
    assert decision.evidence  # deterministic evidence from our code


def test_parse_malformed_response_raises():
    with pytest.raises(JevError):
        parse_jev_response({"answers": {}}, scenarios.too_fast(), "jev-latest")


def test_compact_state_has_no_nulls():
    state = _compact_state(scenarios.too_fast(), "bicep_curl")
    for section in state.values():
        if isinstance(section, dict):
            assert all(v is not None for v in section.values())
    assert "exercise" in state


class _FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return VALID_RESPONSE


class _FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        assert url.endswith("/v1/systemone")
        assert headers["Authorization"].startswith("Bearer ")
        assert json["model"] == "jev-latest"
        assert set(json["questions"]) == {
            "primary_issue",
            "severity",
            "coaching_priority",
            "should_speak",
            "overall_quality",
        }
        return _FakeResponse()


@pytest.mark.asyncio
async def test_decision_service_jev_mode_parses(monkeypatch):
    monkeypatch.setattr(jev_module.httpx, "AsyncClient", _FakeClient)
    settings = Settings(
        decision_provider="jev",
        jev_api_key="test-key",
        jev_base_url="https://api.typesafe.ai",
    )
    decision = await DecisionService(settings).evaluate(scenarios.too_fast())
    assert decision.provider == "jev"
    assert decision.primary_issue is PrimaryIssue.TOO_FAST


@pytest.mark.asyncio
async def test_decision_service_jev_network_error_falls_back(monkeypatch):
    class _BoomClient(_FakeClient):
        async def post(self, *args, **kwargs):
            raise jev_module.httpx.ConnectError("no network")

    monkeypatch.setattr(jev_module.httpx, "AsyncClient", _BoomClient)
    settings = Settings(
        decision_provider="jev",
        jev_api_key="test-key",
        jev_base_url="https://api.typesafe.ai",
    )
    decision = await DecisionService(settings).evaluate(scenarios.too_fast())
    # Must degrade to the rules engine, not crash. The fallback is deliberately simple.
    assert decision.provider == "fallback"
    assert isinstance(decision.primary_issue, PrimaryIssue)
