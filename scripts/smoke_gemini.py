"""One cheap real Gemini request. Run intentionally: `make smoke-gemini`.

Never prints keys. Only runs when GEMINI_API_KEY is set.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402
from app.demo import scenarios  # noqa: E402
from app.models.decisions import (  # noqa: E402
    CoachingPriority,
    MovementDecision,
    OverallQuality,
    PrimaryIssue,
    Severity,
)
from app.services.gemini import LanguageService  # noqa: E402


def main() -> int:
    settings = Settings(language_provider="gemini")
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY is not set. Add it to backend/.env first.")
        return 2

    metrics = scenarios.build_scenario("too_fast")
    decision = MovementDecision(
        primary_issue=PrimaryIssue.TOO_FAST,
        coaching_priority=CoachingPriority.TEMPO,
        severity=Severity.MODERATE,
        should_speak=True,
        overall_quality=OverallQuality.FAIR,
        evidence=["duration_ratio=0.73"],
    )

    print(f"provider: gemini  model: {settings.gemini_model}")
    started = time.perf_counter()
    response = asyncio.run(LanguageService(settings).generate(decision, metrics, "bicep_curl"))
    elapsed = (time.perf_counter() - started) * 1000

    print(f"latency: {elapsed:.0f} ms")
    print(f"provider returned: {response.provider}")
    print(f"text: {response.text}")
    print(f"short_label: {response.short_label}")
    print(f"words: {len(response.text.split())}")

    if response.provider != "gemini":
        print("FAIL: fell back to template — check credentials/network/model id.")
        return 1
    if len(response.text.split()) > 25:
        print("FAIL: coaching text exceeds 25 words.")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
