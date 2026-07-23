#!/usr/bin/env bash
# Full re-seed pipeline — run from inside the activated venv, at project root
# (where manage.py lives).
#
# Usage:
#   source venv/bin/activate
#   ./reseed_all.sh
set -euo pipefail

echo "== 1/7: base data (institute, formes juridiques, expense categories) =="
python manage.py seed_db

echo "== 2/7: core formation catalog + clients + invoices =="
python manage.py seed_formations

echo "== 3/7: sequel P0 =="
python manage.py sequel_formations_seed_p0

echo "== 4/7: sequel P1 =="
python manage.py sequel_formations_seed_p1

echo "== 5/7: sequel P2 =="
python manage.py sequel_formations_seed_p2

echo "== 6/7: sequel P3 =="
python manage.py sequel_formations_seed_p3

echo "== 7/7: sequel P4 =="
python manage.py sequel_formations_seed_p4

echo "✓ Full re-seed completed."