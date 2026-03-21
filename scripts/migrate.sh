#!/usr/bin/env bash
# -------------------------------------------------------------------
# Alembic migration helper — run from project root or inside Docker.
#
# Usage:
#   ./scripts/migrate.sh generate "added vessel_flag column"
#   ./scripts/migrate.sh upgrade
#   ./scripts/migrate.sh downgrade -1
#   ./scripts/migrate.sh history
#
# Inside Docker:
#   docker exec kitagawa-backend /app/scripts/migrate.sh generate "description"
# -------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Alembic needs to run from the backend directory
ALEMBIC_DIR="$PROJECT_ROOT/backend"
export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"

cd "$ALEMBIC_DIR"

case "${1:-help}" in
    generate|gen|auto)
        MSG="${2:?Usage: $0 generate \"migration description\"}"
        echo "[migrate] Generating migration: $MSG"
        alembic revision --autogenerate -m "$MSG"
        echo "[migrate] Done. Check backend/alembic/versions/ for the new file."
        ;;
    upgrade|up)
        TARGET="${2:-head}"
        echo "[migrate] Upgrading to: $TARGET"
        alembic upgrade "$TARGET"
        echo "[migrate] Done."
        ;;
    downgrade|down)
        TARGET="${2:--1}"
        echo "[migrate] Downgrading: $TARGET"
        alembic downgrade "$TARGET"
        echo "[migrate] Done."
        ;;
    history|hist)
        alembic history --verbose
        ;;
    current)
        alembic current
        ;;
    help|*)
        echo "Usage: $0 {generate|upgrade|downgrade|history|current}"
        echo ""
        echo "  generate MSG   Auto-generate a migration from model changes"
        echo "  upgrade [rev]  Apply migrations (default: head)"
        echo "  downgrade [rev] Roll back migrations (default: -1)"
        echo "  history        Show migration history"
        echo "  current        Show current revision"
        ;;
esac
