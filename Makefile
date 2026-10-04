.PHONY: install install-backend install-frontend backend frontend test test-backend build lint smoke smoke-pipeline smoke-gemini smoke-elevenlabs smoke-jev firmware-build firmware-upload imu-monitor imu-record imu-plot imu-analyze clean

install: install-backend install-frontend

install-backend:
	cd backend && uv sync

install-frontend:
	cd frontend && npm install

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test: test-backend build

test-backend:
	cd backend && uv run pytest -q

build:
	cd frontend && npm run build

lint:
	cd frontend && npm run lint

# Real-provider smoke tests. Each consumes (a little) paid quota — run on purpose.
smoke:
	@echo "Run one of: make smoke-pipeline | make smoke-gemini | make smoke-elevenlabs | make smoke-jev"

smoke-pipeline:
	cd backend && uv run python ../scripts/smoke_pipeline.py

smoke-gemini:
	cd backend && uv run python ../scripts/smoke_gemini.py

smoke-elevenlabs:
	cd backend && uv run python ../scripts/smoke_elevenlabs.py

smoke-jev:
	cd backend && uv run python ../scripts/smoke_jev.py

# --- ESP32-C5 wearable firmware (requires PlatformIO) -----------------------
firmware-build:
	cd firmware/esp32-wearable && pio run

firmware-upload:
	cd firmware/esp32-wearable && pio run --target upload

firmware-monitor:
	cd firmware/esp32-wearable && pio device monitor

# --- IMU over BLE (requires the wearable + bleak) ---------------------------
imu-monitor:
	cd backend && uv run python ../scripts/imu_monitor.py

imu-record:
	cd backend && uv run python ../scripts/imu_record.py --name $(NAME) $(if $(SECONDS),--seconds $(SECONDS),)

imu-plot:
	cd backend && uv run python ../scripts/imu_plot.py --file $(FILE) $(if $(SMOOTH),--smooth $(SMOOTH),)

imu-analyze:
	cd backend && uv run python ../scripts/imu_analyze.py --file $(FILE)

clean:
	rm -rf backend/.pytest_cache frontend/dist
