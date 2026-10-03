"""Test isolation: pytest must work with ZERO credentials and never call paid APIs.

These env vars take precedence over backend/.env in pydantic-settings, so even when a
developer has real keys configured locally, the test suite stays offline and free.
"""

import os

os.environ.update(
    {
        "DECISION_PROVIDER": "mock",
        "LANGUAGE_PROVIDER": "mock",
        "VOICE_PROVIDER": "browser",
        "JEV_API_KEY": "",
        "JEV_BASE_URL": "",
        "JEV_API_BASE_URL": "",
        "GEMINI_API_KEY": "",
        "ELEVENLABS_API_KEY": "",
        "ELEVENLABS_VOICE_ID": "",
    }
)
