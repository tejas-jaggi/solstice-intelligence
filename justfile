# Solstice Intelligence — developer task runner (https://just.systems).
#
# CONVENIENCE ONLY. CI and the release workflow run these underlying commands
# directly; `just` never sits between automation and the tools. Precondition: a
# virtual environment is created and activated (see the README Quick Start).

# Show all recipes.
default:
    @just --list

# Install runtime + development dependencies into the active venv.
setup:
    python -m pip install --upgrade pip
    pip install -r requirements.txt -r requirements-dev.txt
    @echo "Deps installed. Copy .env.example to .env, set OPENAI_API_KEY, then: just verify"

# Environment diagnostic (no network, no OpenAI call).
verify:
    python scripts/verify_env.py

# Full deterministic test suite with coverage (mirrors CI).
test:
    pytest --cov --cov-report=term-missing

# Lint (mirrors the CI blocking gate).
lint:
    ruff check .

# Formatting check (mirrors the CI blocking gate).
format-check:
    ruff format --check .

# Apply formatting.
format:
    ruff format .

# Type-check app + frontend (mirrors the CI blocking gate).
typecheck:
    mypy app frontend

# Verify release version consistency (tag <-> pyproject <-> /version).
# Example: just check-version v1.2.4
check-version version:
    python scripts/check_version.py {{version}}

# Start the backend API with reload.
run-api:
    python -m uvicorn app.api.main:app --reload

# Start the Streamlit frontend.
run-ui:
    streamlit run frontend/streamlit_app.py
