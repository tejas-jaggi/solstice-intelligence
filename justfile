# Solstice Intelligence — developer task runner.
#
# Convenience only.
# CI runs the underlying commands directly.
# Precondition:
#   - Virtual environment is created and activated.
#   - See README Quick Start for initial bootstrap.

default:
    @just --list

# Install runtime + development dependencies.
setup:
    python -m pip install --upgrade pip
    pip install -r requirements.txt -r requirements-dev.txt
    @echo "Dependencies installed."
    @echo "Next:"
    @echo "  1. Copy .env.example to .env"
    @echo "  2. Set OPENAI_API_KEY"
    @echo "  3. Run: just verify"

# Environment diagnostics.
verify:
    python scripts/verify_env.py

# Full deterministic test suite.
test:
    pytest --cov --cov-report=term-missing

# Ruff lint.
lint:
    ruff check .

# Verify formatting.
format-check:
    ruff format --check .

# Apply formatting.
format:
    ruff format .

# Static typing.
typecheck:
    mypy app frontend

# Run backend.
run-api:
    python -m uvicorn app.api.main:app --reload

# Run frontend.
run-ui:
    streamlit run frontend/streamlit_app.py