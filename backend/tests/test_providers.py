import pytest

from app.config import Settings
from app.demo import scenarios
from app.models.decisions import CoachingPriority, MovementDecision, PrimaryIssue, Severity
from app.services.elevenlabs import VoiceService
from app.services.gemini import LanguageService


def _decision() -> MovementDecision:
    return MovementDecision(
        primary_issue=PrimaryIssue.TOO_FAST,
        coaching_priority=CoachingPriority.TEMPO,
        severity=Severity.MODERATE,
        should_speak=True,
        overall_quality="FAIR",
    )


@pytest.mark.asyncio
async def test_voice_browser_mode_returns_browser():
    result = await VoiceService(Settings(voice_provider="browser")).synthesize("hello")
    assert result.provider == "browser"
    assert result.audio is None


@pytest.mark.asyncio
async def test_voice_elevenlabs_without_key_falls_back():
    result = await VoiceService(Settings(voice_provider="elevenlabs")).synthesize("hello")
    assert result.provider == "browser"
    assert result.audio is None


@pytest.mark.asyncio
async def test_language_gemini_without_key_uses_template():
    settings = Settings(language_provider="gemini", gemini_api_key="")
    response = await LanguageService(settings).generate(_decision(), scenarios.too_fast(), "bicep_curl")
    assert response.provider == "fallback"
    assert response.text
    assert len(response.text.split()) <= 25


@pytest.mark.asyncio
async def test_language_mock_provider():
    response = await LanguageService(Settings(language_provider="mock")).generate(
        _decision(), scenarios.too_fast(), "bicep_curl"
    )
    assert response.provider == "mock"
