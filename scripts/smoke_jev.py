"""Real Jev decision smoke test — gated until the provider contract is verified.

This script refuses to make a request until the contract has been confirmed in
docs/JEV_PROVIDER.md. It will not guess an endpoint or schema.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402
from app.demo import scenarios  # noqa: E402
from app.services.jev import DecisionService  # noqa: E402


def main() -> int:
    settings = Settings(decision_provider="jev")
    if not (settings.jev_api_key and settings.jev_base_url):
        print("JEV_API_KEY / JEV_BASE_URL not set. See docs/JEV_PROVIDER.md.")
        return 2

    print(f"provider: {settings.jev_base_url}  model: {settings.jev_model or '(unset)'}")
    metrics = scenarios.build_scenario("too_fast")
    decision = asyncio.run(DecisionService(settings).evaluate(metrics))

    print(f"decided by: {decision.provider}")
    print(f"primary_issue: {decision.primary_issue.value}")
    print(f"severity: {decision.severity.value}")
    print(f"confidence: {decision.confidence}")
    print(f"evidence: {decision.evidence}")
    print(f"latency: {decision.latency_ms} ms")

    if decision.provider != "jev":
        print(
            "FAIL: provider did not return a Jev decision. The real adapter is not "
            "implemented until the contract is verified (docs/JEV_PROVIDER.md)."
        )
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
