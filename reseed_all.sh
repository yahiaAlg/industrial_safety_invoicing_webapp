#!/usr/bin/env bash
# Full re-seed pipeline — run from inside the activated venv, at project root
# (where manage.py lives).
#
# Usage:
#   source venv/bin/activate
#   ./reseed_all.sh
#
# Invoice numbering (proforma_reference) is generated from a shared,
# per-year sequence. The sequel scripts force that sequence to specific
# historical numbers, so any leftover invoices from a previous partial
# run WILL collide. We therefore always flush invoices/sequences first —
# clients and formations are left untouched (get_or_create, safe to reuse).
set -euo pipefail

echo "== 0/7: flush invoices & sequences (clients/formations kept) =="
python manage.py shell -c "
from financial.models import Invoice, InvoiceItem, InvoiceSequence
InvoiceItem.objects.all().delete()
Invoice.objects.all().delete()
InvoiceSequence.objects.all().delete()
print('  ✓ Invoice / InvoiceItem / InvoiceSequence cleared')
"



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