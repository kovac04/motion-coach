from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["providers"]) == {"decision", "language", "voice"}


def test_scenarios_listing():
    response = client.get("/api/demo/scenarios")
    assert response.status_code == 200
    ids = {s["id"] for s in response.json()}
    assert {"perfect_set", "too_fast", "inconsistent"} <= ids


def test_scenario_detail_and_evaluate_set():
    metrics = client.get("/api/demo/scenarios/too_fast").json()
    response = client.post("/api/evaluate/set", json=metrics)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["primary_issue"] == "TOO_FAST"
    assert body["coaching"]["text"]


def test_unknown_scenario_returns_404():
    assert client.get("/api/demo/scenarios/nope").status_code == 404


def test_evaluate_rep():
    rep = {
        "exercise_id": "bicep_curl",
        "rep_number": 1,
        "duration_ms": 1500,
        "reference_duration_ms": 2000,
        "rom_deg": 118,
        "reference_rom_deg": 120,
    }
    response = client.post("/api/evaluate/rep", json=rep)
    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["duration_ratio"] == 0.75


def test_invalid_metrics_rejected():
    response = client.post("/api/evaluate/set", json={"exercise_id": "x", "rep_count": 1, "reps": []})
    assert response.status_code == 422


def test_sensor_status_offline():
    response = client.get("/api/sensor/status")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body["device_name"] == "MotionCoach-IMU"
    assert "sample_rate_hz" in body
    assert body["sample"] is None


def test_custom_set_endpoint():
    response = client.post(
        "/api/demo/custom",
        json={"exercise_id": "bicep_curl", "duration_ratio": 0.8, "rom_ratio": 1.0,
              "similarity": 0.9, "smoothness": 0.9, "variability": 0.02, "rep_count": 4},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["rep_count"] == 4
    assert body["metadata"]["scenario"] == "custom"


def test_tts_without_elevenlabs_uses_browser_fallback():
    response = client.post("/api/tts", json={"text": "Slow down and control the tempo."})
    assert response.status_code == 502
    assert response.json()["detail"]["voice_provider"] == "browser"


def test_providers_do_not_leak_secrets():
    response = client.get("/api/providers")
    assert response.status_code == 200
    assert "api_key" not in response.text.lower()
