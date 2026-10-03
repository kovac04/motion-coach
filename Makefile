.PHONY: install install-backend install-frontend backend frontend test test-backend build lint smoke smoke-pipeline smoke-gemini smoke-elevenlabs smoke-jev clean

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

clean:
	rm -rf backend/.pytest_cache frontend/dist
