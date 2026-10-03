"""Offline end-to-end smoke test: all scenarios -> decision -> coaching.

No credentials required. Run with `make smoke-pipeline`.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402
from app.demo import scenarios  # noqa: E402
from app.services.coach_pipeline import CoachPipeline  # noqa: E402


async def run() -> int:
    # Offline by default so it never spends credits. Set SMOKE_REAL=1 to use .env providers.
    if os.environ.get("SMOKE_REAL") == "1":
        settings = Settings()
    else:
        settings = Settings(
            decision_provider="mock", language_provider="mock", voice_provider="disabled"
        )
    pipeline = CoachPipeline(settings)
    failures = 0

    print(f"decision={settings.decision_provider} language={settings.language_provider} "
          f"voice={settings.voice_provider}\n")

    for summary in scenarios.list_scenario_summaries():
        metrics = scenarios.build_scenario(summary["id"])
        result = await pipeline.evaluate(metrics)
        words = len(result.coaching.text.split())
        ok = bool(result.coaching.text) and words <= 25
        failures += 0 if ok else 1
        print(
            f"[{'ok' if ok else 'FAIL'}] {summary['id']:<15} "
            f"{result.decision.primary_issue.value:<16} "
            f"{result.decision.severity.value:<8} "
            f"decision={result.decision.latency_ms:.1f}ms "
            f"coach={result.coaching.latency_ms:.1f}ms\n"
            f"      \"{result.coaching.text}\""
        )

    print(f"\n{'ALL GOOD' if failures == 0 else f'{failures} FAILURES'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
