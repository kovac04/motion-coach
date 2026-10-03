"""Real TypeSafe Jev smoke test. Run intentionally: `make smoke-jev`.

Sends one obvious TOO_FAST set and one GOOD set, verifies parsing into our
MovementDecision, and prints latency/model. Never prints keys.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402
from app.demo import scenarios  # noqa: E402
from app.services.jev import DecisionService  # noqa: E402


async def check(service: DecisionService, scenario_id: str) -> bool:
    metrics = scenarios.build_scenario(scenario_id)
    decision = await service.evaluate(metrics)
    print(f"\n[{scenario_id}] decided by: {decision.provider}")
    print(f"  primary_issue: {decision.primary_issue.value}")
    print(f"  severity: {decision.severity.value}  priority: {decision.coaching_priority.value}")
    print(f"  should_speak: {decision.should_speak}  quality: {decision.overall_quality.value}")
    print(f"  confidence: {decision.confidence}")
    print(f"  alternatives: {decision.alternatives}")
    print(f"  model: {decision.model_version}  latency: {decision.latency_ms:.0f} ms")
    if decision.provider != "jev":
        print("  FAIL: fell back — check key/base URL/model/network.")
        return False
    return True


async def run() -> int:
    settings = Settings(decision_provider="jev")
    if not settings.jev_api_key or not settings.jev_base_url:
        print("JEV_API_KEY / JEV_API_BASE_URL not set. See docs/JEV_PROVIDER.md.")
        return 2

    print(f"provider: {settings.jev_base_url}/v1/systemone  model: {settings.jev_model}")
    service = DecisionService(settings)
    results = [
        await check(service, "too_fast"),
        await check(service, "perfect_set"),
    ]
    print("\nOK" if all(results) else "\nFAILURES")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
