import pytest

from app.config import Settings
from app.demo import scenarios
from app.models.decisions import OverallQuality, PrimaryIssue, Severity
from app.motion.assessment import assess
from app.services import jev as jev_module
from app.services.jev import DecisionService, JevError, _compact_state, parse_jev_response


def _fast_metrics():
    from app.models.metrics import RepMetrics, build_set_metrics
    reps = [
        RepMetrics(exercise_id="bicep_curl", rep_number=i, duration_ms=1400,
                   reference_duration_ms=2000, rom_deg=120, reference_rom_deg=120)
        for i in range(1, 6)
    ]
    return build_set_metrics("bicep_curl", reps)


def _response(severity_score=1.4, primary=None, speak=0.9):
    answers = {
        "severity": {
            "type": "score", "score": severity_score, "confidence": 0.7,
            "legend": {str(i): lvl for i, lvl in enumerate(["none", "mild", "moderate", "major"])},
            "probabilities": {},
        },
    }
    if primary is not None:
        answers["primary_issue"] = {
            "type": "choice", "choice": primary, "confidence": 0.91,
            "probabilities": {primary: 0.82, "good": 0.18},
        }
    return {"model": "jev-1.13.0", "answers": answers, "usage": {}}


def test_single_candidate_parses_without_asking_primary():
    metrics = _fast_metrics()
    assessment = assess(metrics)
    assert assessment.candidates == [PrimaryIssue.TOO_FAST]
    decision = parse_jev_response(_response(), metrics, "jev-latest", assessment, asked_primary=False)
    assert decision.primary_issue is PrimaryIssue.TOO_FAST
    assert decision.should_speak is True
    assert decision.overall_quality is OverallQuality.GOOD  # severity score 1.4 -> MILD -> GOOD
    assert decision.provider == "jev"


def test_jev_cannot_choose_an_unestablished_issue():
    metrics = _fast_metrics()
    assessment = assess(metrics)
    # Jev answers INSUFFICIENT_ROM even though only TOO_FAST was established.
    decision = parse_jev_response(
        _response(primary="insufficient_rom"), metrics, "jev-latest",
        assessment, asked_primary=True,
    )
    assert decision.primary_issue is PrimaryIssue.TOO_FAST


def test_multi_candidate_question_set():
    # Construct a set that is both too fast and short-ROM.
    from app.models.metrics import RepMetrics, build_set_metrics

    reps = [
        RepMetrics(exercise_id="bicep_curl", rep_number=i, duration_ms=1400,
                   reference_duration_ms=2000, rom_deg=95, reference_rom_deg=120)
        for i in range(1, 6)
    ]
    metrics = build_set_metrics("bicep_curl", reps)
    assessment = assess(metrics)
    assert PrimaryIssue.TOO_FAST in assessment.candidates
    assert PrimaryIssue.INSUFFICIENT_ROM in assessment.candidates

    questions = jev_module._build_questions(assessment)
    assert set(questions) == {"severity", "primary_issue"}
    assert set(questions["primary_issue"]["criteria"]) == {"too_fast", "insufficient_rom"}

    # Jev picks the ROM issue; that is allowed because it is a candidate.
    decision = parse_jev_response(_response(primary="insufficient_rom"), metrics,
                                  "jev-latest", assessment, asked_primary=True)
    assert decision.primary_issue is PrimaryIssue.INSUFFICIENT_ROM


def test_good_set_never_reaches_jev():
    metrics = scenarios.perfect_set()
    assessment = assess(metrics)
    assert assessment.candidates == []

    # evaluate() with jev mode and no credentials must still return deterministic GOOD
    # without attempting a Jev call.
    import asyncio

    settings = Settings(decision_provider="jev", jev_api_key="", jev_base_url="")
    decision = asyncio.run(DecisionService(settings).evaluate(metrics))
    assert decision.primary_issue is PrimaryIssue.GOOD
    assert decision.should_speak is False
    assert decision.severity is Severity.NONE


def test_compact_state_has_no_nulls_and_lists_candidates():
    assessment = assess(_fast_metrics())
    state = _compact_state(_fast_metrics(), "bicep_curl", assessment)
    assert state["candidate_issues"] == ["TOO_FAST"]
    assert "detected_deviations" in state
    # The standard sections hold only non-null facts; the deviations section may
    # legitimately carry null medians (e.g. no similarity measured).
    for name, section in state.items():
        if isinstance(section, dict) and name != "detected_deviations":
            assert all(v is not None for v in section.values())


class _FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    payload = _response()
    seen_questions = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        assert url.endswith("/v1/systemone")
        _FakeClient.seen_questions = set(json["questions"])
        return _FakeResponse(_FakeClient.payload)


@pytest.mark.asyncio
async def test_decision_service_jev_mode_parses(monkeypatch):
    monkeypatch.setattr(jev_module.httpx, "AsyncClient", _FakeClient)
    settings = Settings(decision_provider="jev", jev_api_key="test-key",
                        jev_base_url="https://api.typesafe.ai")
    decision = await DecisionService(settings).evaluate(_fast_metrics())
    assert decision.provider == "jev"
    assert decision.primary_issue is PrimaryIssue.TOO_FAST
    # single candidate -> only severity was asked
    assert _FakeClient.seen_questions == {"severity"}


@pytest.mark.asyncio
async def test_decision_service_jev_network_error_falls_back(monkeypatch):
    class _BoomClient(_FakeClient):
        async def post(self, *args, **kwargs):
            raise jev_module.httpx.ConnectError("no network")

    monkeypatch.setattr(jev_module.httpx, "AsyncClient", _BoomClient)
    settings = Settings(decision_provider="jev", jev_api_key="test-key",
                        jev_base_url="https://api.typesafe.ai")
    decision = await DecisionService(settings).evaluate(_fast_metrics())
    assert decision.provider == "fallback"
    assert decision.primary_issue is PrimaryIssue.TOO_FAST
