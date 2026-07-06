# ISI Backend - Système de Gestion de l'Institut de Sécurité Industrielle

A Django backend implementation for an Industrial Safety Institute management system.

## Features

### Business Lines

- **Formations** - Professional safety training & certification
- **Études** - Industrial safety consulting & study projects

### Core Modules

- **Clients** - Client records, contact info, activity history
- **Formations** - Training catalog, sessions, enrollments, attestations
- **Études** - Study projects, phases, deliverables
- **Financial** - Invoices, payments, expenses
- **Resources** - Trainers, rooms, equipment, maintenance logs
- **Reporting** - Dashboard, KPIs, revenue reports

### User Roles

- **Administrateur** - Full access to all modules and financials
- **Réceptionniste** - Data entry access only (clients, enrollments, basic project info)

## Project Structure

```
config/
├── config/          # Project settings
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── core/                 # Institute information
│   ├── models.py         # InstituteInfo, BureauEtudeInfo, FormationInfo
│   ├── admin.py
│   └── context_processors.py
├── accounts/             # User authentication & profiles
│   ├── models.py         # UserProfile
│   ├── signals.py
│   ├── forms.py
│   ├── views.py
│   └── urls.py
├── clients/              # Client management
│   ├── models.py
│   ├── forms.py
│   ├── views.py
│   └── urls.py
├── formations/           # Training management
│   ├── models.py         # Formation, Session, Participant, Attestation
│   ├── forms.py
│   ├── views.py
│   └── urls.py
├── etudes/               # Study projects
│   ├── models.py         # StudyProject, ProjectPhase, ProjectDeliverable
│   ├── forms.py
│   ├── views.py
│   └── urls.py
├── financial/            # Invoicing & expenses
│   ├── models.py         # Invoice, Payment, Expense
│   ├── forms.py
│   ├── views.py
│   └── urls.py
├── resources/            # Resources management
│   ├── models.py         # Trainer, TrainingRoom, Equipment, EquipmentUsage, MaintenanceLog
│   ├── forms.py
│   ├── views.py
│   └── urls.py
└── reporting/            # Dashboard & reports
    ├── views.py
    └── urls.py
```

## Installation

1. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run migrations:

```bash
python manage.py migrate
```

4. Create a superuser:

```bash
python manage.py createsuperuser
```

5. Run the development server:

```bash
python manage.py runserver
```

## Configuration

### Institute Information

After creating the superuser, access the Django admin at `/admin/` and configure:

1. **InstituteInfo** - General institute information (name, address, TVA, etc.)
2. **BureauEtudeInfo** - Consulting-specific information
3. **FormationInfo** - Training-specific information

### TVA Rate

The default TVA rate is 19% (Algerian standard). This can be configured in:

- `settings.py` - `TVA_RATE` setting
- Individual business line settings in `BureauEtudeInfo` and `FormationInfo`

## Business Rules

1. A session cannot be invoiced before its status is "Terminée"
2. A project phase should be marked complete before the project is closed
3. Participants cannot be enrolled beyond session capacity
4. Invoice numbers are auto-generated, sequential, and unique per business line
5. TVA is applied on all invoices (standard Algerian rate)
6. Currency: Algerian Dinar (DA)

## API Endpoints

### Accounts

- `GET/POST /accounts/login/` - Login
- `POST /accounts/logout/` - Logout
- `GET /accounts/users/` - User list (admin only)
- `GET/POST /accounts/users/create/` - Create user (admin only)
- `GET/POST /accounts/users/<id>/edit/` - Edit user (admin only)

### Clients

- `GET /clients/` - Client list
- `GET/POST /clients/create/` - Create client
- `GET /clients/<id>/` - Client detail
- `GET/POST /clients/<id>/edit/` - Edit client
- `POST /clients/<id>/delete/` - Delete client (admin only)

### Formations

- `GET /formations/` - Formation catalog
- `GET /formations/sessions/` - Session list
- `GET /formations/sessions/<id>/` - Session detail
- `GET/POST /formations/sessions/create/` - Create session (admin only)
- `GET/POST /formations/sessions/<id>/participants/add/` - Add participant
- `GET /formations/participants/<id>/attestation/` - View attestation

### Financial

- `GET /financial/invoices/` - Invoice list (admin only)
- `GET /financial/invoices/<id>/` - Invoice detail (admin only)
- `GET /financial/invoices/<id>/print/` - Printable invoice (admin only)
- `GET /financial/outstanding/` - Outstanding payments (admin only)
- `GET /financial/expenses/` - Expense list (admin only)

### Reporting

- `GET /` - Dashboard
- `GET /reporting/revenue/` - Revenue report (admin only)
- `GET /reporting/margins/` - Margins report (admin only)

## Print Templates

The system uses HTML/CSS templates for printable documents:

- **Invoices** - `/financial/invoices/<id>/print/` with print-specific CSS
- **Attestations** - `/formations/participants/<id>/attestation/`

Use `@media print` CSS rules for print optimization.

## Development Notes

### Function-Based Views

All views are implemented as function-based views following Django best practices.

### Post-Redirect-Get Pattern

All POST requests redirect to a GET request to prevent duplicate submissions.

### Minimal AJAX

AJAX is used sparingly via `JsonResponse` only when explicitly required.

### Role-Based Access

Views check `request.user.profile.is_admin` to restrict access to financial data.

## License

Proprietary - Institut de Sécurité Industrielle

# Run from your project root (Git Bash)

```bash
find . -path "./.venv" -prune -o -path "*/migrations/0*.py" -print | xargs rm -f

python manage.py makemigrations core clients accounts etudes formations resources financial

rm -f db.sqlite3

python manage.py migrate

python manage.py seed_db_minimal

python manage.py seed_formations_catalog     # all 505 specialties
```

---

Now let me find the `dashboard_kpis` function specifically:

Now let me check the `dashboard_kpis` utility for the gross margin formula:

I now have everything needed. Here's the complete breakdown:

---

## How Each Dashboard Metric is Calculated

### 1. CA HT (Année) — `4 744 661 DA`

**Source:** `dashboard_kpis()` → `financial/utils.py`

```
CA HT = SUM(Invoice.amount_ht)
        WHERE phase = FINALE
          AND status IN [UNPAID, PARTIALLY_PAID, PAID]
          AND invoice_date IN current year range
```

This is **billed revenue** — all finalized invoices issued this year, regardless of whether they've been paid. Broken down as `F 4 744 661 · E 0` (Formations · Études).

---

### 2. Encaissé (Année) — `3 591 100 DA`

```
Encaissé = SUM(Payment.amount)
           WHERE status = CONFIRMED
             AND date IN current year range
```

**Actual cash received** — only confirmed payments. This is always ≤ CA HT because some invoices are still unpaid.

---

### 3. Créances impayées — `1 549 980 DA`

```
Créances = SUM(Invoice.amount_remaining)
           WHERE status IN [UNPAID, PARTIALLY_PAID]
```

`amount_remaining` is a stored field on the `Invoice` model: `amount_ttc − amount_paid`. This is the **outstanding receivables** — money billed but not yet collected.

**Note:** CA HT − Encaissé ≠ Créances exactly, because CA is HT (excl. TVA) while payments and remaining are TTC (incl. TVA).

---

### 4. Marge Brute — `−3 802 180 DA` ⚠️

```python
# From FinancialPeriod model (master_models.md line 2740):
gross_margin = total_invoiced_ht - total_expenses

# Where:
total_invoiced_ht = SUM(Invoice.amount_ht) — finalized invoices, current year
total_expenses    = SUM(Expense.amount)    — WHERE approval_status = APPROVED
                                             AND date IN current year
```

**Why it's negative:** Approved expenses (`8 546 841 DA`) far exceed invoiced HT revenue (`4 744 661 DA`). This is mathematically correct — the institute spent more than it billed.

**Important nuance about `Expense.amount`:**

```python
# Expense.save():
amount = gross_amount + irg_amount   # = gross + (gross × irg_rate)
# IRG is an ADDITIONAL tax paid to the State on top of what's paid to the provider
```

So expenses include the IRG withholding tax burden.

---

### 5. Flux de trésorerie NET — `−4 955 741 DA`

```python
# Per month: net = collected - expenses
# Running balance = cumulative sum of monthly nets

net = SUM(Payment.amount WHERE status=CONFIRMED)
    − SUM(Expense.amount WHERE approval_status=APPROVED)
```

This is a **cash basis** calculation (actual payments received vs. actual expenses incurred by date). It's more negative than the gross margin because Encaissé (3 591 100) < CA HT (4 744 661).

---

## What's Missing: The "Real Revenue" Metric You Want

You're looking for:

```
Real Result = Approved & Paid Invoices (HT) − Approved Expenses
```

**Currently, no single metric does this cleanly.** Here's the mismatch:

| Metric        | Revenue side         | Expense side      | Problem                            |
| ------------- | -------------------- | ----------------- | ---------------------------------- |
| Marge Brute   | Invoiced HT (billed) | Approved expenses | Includes unpaid invoices           |
| Cash Flow NET | Collected TTC (paid) | Approved expenses | Mixes HT revenue with TTC payments |

The correct formula would be:

```python
real_result = SUM(Invoice.amount_ht
                  WHERE status = PAID
                    AND invoice_date IN period)
            - SUM(Expense.amount
                  WHERE approval_status = APPROVED
                    AND date IN period)
```

This would use only **fully paid invoices (HT)** against **approved expenses** — giving you a true operational result on a revenue-recognition basis. This doesn't exist yet in `reporting_views.py` and would need to be added as a new view/metric.

---

Now I have everything I need. Here's the Django financial summary shell script:

```python
from decimal import Decimal
from django.db.models import Sum, Q
from financial.models import Expense, Invoice, Payment

# ── Expenses ──────────────────────────────────────────────────────────────────

approved_expenses = (
    Expense.objects.filter(approval_status=Expense.ApprovalStatus.APPROVED)
    .aggregate(total=Sum("amount"))["total"] or Decimal("0")
)

total_expenses = (
    Expense.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0")
)

expenses_difference = total_expenses - approved_expenses  # pending + rejected

# ── Invoices (finale only) ────────────────────────────────────────────────────

invoices_ht_total = (
    Invoice.objects.filter(
        phase=Invoice.Phase.FINALE,
    )
    .exclude(status=Invoice.Status.VOIDED)
    .aggregate(total=Sum("amount_ht"))["total"] or Decimal("0")
)

# ── Payments (confirmed only) ─────────────────────────────────────────────────

payments_total = (
    Payment.objects.filter(status=Payment.Status.CONFIRMED)
    .aggregate(total=Sum("amount"))["total"] or Decimal("0")
)

# ── Margins ───────────────────────────────────────────────────────────────────

profit                = invoices_ht_total - approved_expenses   # billed HT − approved costs
current_margin        = payments_total - approved_expenses      # cash received − approved costs
theoretical_margin    = invoices_ht_total - total_expenses      # total HT − all costs

# ── Report ────────────────────────────────────────────────────────────────────

print("=" * 55)
print(f"  Approved expenses          : {approved_expenses:>14,.2f} DA")
print(f"  Total expenses             : {total_expenses:>14,.2f} DA")
print(f"  Difference (non-approved)  : {expenses_difference:>14,.2f} DA")
print("-" * 55)
print(f"  Invoices HT total          : {invoices_ht_total:>14,.2f} DA")
print(f"  Payments total (confirmed) : {payments_total:>14,.2f} DA")
print("-" * 55)
print(f"  Profit (HT − approved)     : {profit:>14,.2f} DA")
print(f"  Current margin (pay−appr.) : {current_margin:>14,.2f} DA")
print(f"  Theoretical margin         : {theoretical_margin:>14,.2f} DA")
print("=" * 55)
```

**Key choices made:**

- `Expense.amount` is used (the full org cost = gross + IRG), not `gross_amount`
- Invoices are filtered to `phase=FINALE` and voided ones are excluded, since proformas aren't real revenue
- Only `Payment.Status.CONFIRMED` payments count toward `payments_total` (pending/reversed excluded)
- `expenses_difference` = total − approved, meaning it captures pending + rejected expenses

---

```python
from decimal import Decimal
from django.db.models import Sum
from financial.models import Expense, Invoice, Payment

# ── Expenses ──────────────────────────────────────────────────────────────────

approved_expenses = (
    Expense.objects.filter(approval_status=Expense.ApprovalStatus.APPROVED)
    .aggregate(total=Sum("amount"))["total"] or Decimal("0")
)

total_expenses = (
    Expense.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0")
)

expenses_difference = total_expenses - approved_expenses  # pending + rejected

# ── Invoices (finale, non-voided) ─────────────────────────────────────────────

invoice_qs = Invoice.objects.filter(
    phase=Invoice.Phase.FINALE,
).exclude(status=Invoice.Status.VOIDED)

invoice_totals = invoice_qs.aggregate(
    ht=Sum("amount_ht"),
    tva=Sum("amount_tva"),
    ttc=Sum("amount_ttc"),
)

invoices_ht_total  = invoice_totals["ht"]  or Decimal("0")
invoices_tva_total = invoice_totals["tva"] or Decimal("0")
invoices_ttc_total = invoice_totals["ttc"] or Decimal("0")

# ── Payments (confirmed only) ─────────────────────────────────────────────────

payments_total = (
    Payment.objects.filter(status=Payment.Status.CONFIRMED)
    .aggregate(total=Sum("amount"))["total"] or Decimal("0")
)

# ── Margins — HT base ────────────────────────────────────────────────────────

profit             = invoices_ht_total  - approved_expenses   # billed HT − approved costs
current_margin     = payments_total     - approved_expenses   # cash received − approved costs
theoretical_margin = invoices_ht_total  - total_expenses      # total HT − all costs

# ── Margins — TTC base ───────────────────────────────────────────────────────

profit_ttc             = invoices_ttc_total - approved_expenses   # billed TTC − approved costs
current_margin_ttc     = payments_total     - approved_expenses   # same (payments are TTC amounts)
theoretical_margin_ttc = invoices_ttc_total - total_expenses      # total TTC − all costs

# ── Report ────────────────────────────────────────────────────────────────────

W = 57
print("=" * W)
print(f"  {'EXPENSES'}")
print(f"  Approved expenses            : {approved_expenses:>14,.2f} DA")
print(f"  Total expenses               : {total_expenses:>14,.2f} DA")
print(f"  Difference (non-approved)    : {expenses_difference:>14,.2f} DA")
print("-" * W)
print(f"  {'INVOICES (finale, non-voided)'}")
print(f"  Total HT                     : {invoices_ht_total:>14,.2f} DA")
print(f"  Total TVA                    : {invoices_tva_total:>14,.2f} DA")
print(f"  Total TTC                    : {invoices_ttc_total:>14,.2f} DA")
print(f"  Payments total (confirmed)   : {payments_total:>14,.2f} DA")
print("-" * W)
print(f"  {'MARGINS — HT BASE'}")
print(f"  Profit      (HT  − approved) : {profit:>14,.2f} DA")
print(f"  Current     (pay − approved) : {current_margin:>14,.2f} DA")
print(f"  Theoretical (HT  − total)    : {theoretical_margin:>14,.2f} DA")
print("-" * W)
print(f"  {'MARGINS — TTC BASE'}")
print(f"  Profit      (TTC − approved) : {profit_ttc:>14,.2f} DA")
print(f"  Current     (pay − approved) : {current_margin_ttc:>14,.2f} DA")
print(f"  Theoretical (TTC − total)    : {theoretical_margin_ttc:>14,.2f} DA")
print("=" * W)
```

**Note on TTC margins:** `current_margin` is identical in both bases because `Payment.amount` records the actual cash received (TTC amounts) — it has no separate HT/TTC split. The difference between HT and TTC bases only shows up in `profit` and `theoretical_margin`.
