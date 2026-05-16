#!/usr/bin/env bash
# AutoSentiment — one-command project setup
#
# Usage: ./setup.sh
#
# Creates Python venv, installs backend + frontend deps, copies .env.example,
# initializes the database, and prints next steps.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AutoSentiment Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Python backend ──────────────────────────────────────────────────────
echo ""
echo "→ Setting up Python backend…"
cd "$ROOT/backend"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "  ✓ Created .venv"
else
    echo "  • .venv already exists"
fi

source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "  ✓ Python dependencies installed"

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  ✓ Created .env from .env.example — EDIT IT to add your BRAVE_API_KEY"
else
    echo "  • .env already exists"
fi

# ── Node frontend ───────────────────────────────────────────────────────
echo ""
echo "→ Setting up frontend…"
cd "$ROOT/frontend"
npm install --silent 2>/dev/null || npm install
echo "  ✓ npm dependencies installed"

# ── Database ────────────────────────────────────────────────────────────
echo ""
echo "→ Initializing database…"
cd "$ROOT/backend"
source .venv/bin/activate
python3 -c "
import asyncio
from app.db.session import create_tables
asyncio.run(create_tables())
" 2>/dev/null && echo "  ✓ Database tables created" || echo "  ⚠ Database init skipped (will auto-create on first run)"

# ── Verify ──────────────────────────────────────────────────────────────
echo ""
echo "→ Running quick verification…"
cd "$ROOT/backend"
source .venv/bin/activate
if timeout 15 python3 -m pytest tests/test_fetch.py tests/test_search.py tests/test_research_depth.py -q 2>/dev/null; then
    echo "  ✓ Core tests pass"
else
    echo "  ⚠ Some tests did not run (models may not be loaded in Ollama)"
fi

cd "$ROOT/frontend"
if npx tsc --noEmit 2>/dev/null; then
    echo "  ✓ TypeScript check passes"
else
    echo "  ⚠ TypeScript check had issues (may need npm install)"
fi

# ── Done ────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Edit backend/.env — add your BRAVE_API_KEY"
echo "  2. Start backend:  cd backend && source .venv/bin/activate && uvicorn app.main:app --reload"
echo "  3. Start frontend: cd frontend && npm run dev"
echo "  4. Open http://localhost:5173"
echo ""
echo "  Optional:"
echo "  • Set AUTH_API_KEY in .env to enable API authentication"
echo "  • Set ENABLE_MEDIA_API_SEARCH=true to use free supplemental sources"
echo "  • Run all tests: cd backend && source .venv/bin/activate && pytest tests/ -v"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
