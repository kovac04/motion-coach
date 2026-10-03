import pytest

from app.demo import scenarios
from app.models.decisions import PrimaryIssue, Severity
from app.services.jev import mock_decision


@pytest.mark.parametrize(
    "scenario_id,expected_issue",
    [
        ("perfect_set", PrimaryIssue.GOOD),
        ("too_fast", PrimaryIssue.TOO_FAST),
        ("too_slow", PrimaryIssue.TOO_SLOW),
        ("low_rom", PrimaryIssue.INSUFFICIENT_ROM),
        ("inconsistent", PrimaryIssue.INCONSISTENT),
        ("fatigue_drift", PrimaryIssue.INCONSISTENT),
    ],
)
def test_mock_scenario_decisions(scenario_id, expected_issue):
    metrics = scenarios.build_scenario(scenario_id)
    decision = mock_decision(metrics)
    assert decision.primary_issue is expected_issue
    assert decision.provider == "mock"
    assert decision.evidence
    assert decision.confidence is not None and 0.0 <= decision.confidence <= 1.0


def test_perfect_set_does_not_speak_correction():
    decision = mock_decision(scenarios.build_scenario("perfect_set"))
    assert decision.severity is Severity.NONE
    assert decision.alternatives.get("GOOD", 0) > 0.5


def test_scenario_catalog_matches_builders():
    summaries = scenarios.list_scenario_summaries()
    assert len(summaries) == 6
    for summary in summaries:
        metrics = scenarios.build_scenario(summary["id"])
        assert metrics.rep_count == len(metrics.reps)
