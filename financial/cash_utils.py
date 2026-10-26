"""Cash journal helpers: amount in French words, period resolution, statement."""

import calendar
import unicodedata
from datetime import date
from decimal import Decimal

from django.db.models import Sum

_ONES = [
    "zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
    "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
    "dix-sept", "dix-huit", "dix-neuf",
]
_TENS = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}
MONTHS_FR = [
    "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
    "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


def _fold(text: str) -> str:
    """Lowercase + strip accents, for forgiving text search."""
    return "".join(
        c for c in unicodedata.normalize("NFD", (text or "").casefold())
        if unicodedata.category(c) != "Mn"
    )


def _under_100(n: int, final: bool) -> str:
    if n < 17:
        return _ONES[n]
    if n < 20:
        return _ONES[n]
    t, o = divmod(n, 10)
    if t in _TENS:
        if o == 0:
            return _TENS[t]
        return f"{_TENS[t]}-et-un" if o == 1 else f"{_TENS[t]}-{_ONES[o]}"
    if t == 7:
        return "soixante-et-onze" if o == 1 else f"soixante-{_ONES[10 + o]}"
    if t == 8:
        return ("quatre-vingts" if final else "quatre-vingt") if o == 0 else f"quatre-vingt-{_ONES[o]}"
    return f"quatre-vingt-{_ONES[10 + o]}"  # 90-99


def _under_1000(n: int, final: bool) -> str:
    """`final` = nothing (except a noun like 'million') follows → vingts/cents take an s."""
    h, rem = divmod(n, 100)
    parts = []
    if h == 1:
        parts.append("cent")
    elif h > 1:
        parts.append(f"{_ONES[h]} cent{'s' if (rem == 0 and final) else ''}")
    if rem:
        parts.append(_under_100(rem, final))
    return " ".join(parts)


def number_to_words_fr(n: int) -> str:
    if n == 0:
        return "zéro"
    groups = []
    milliards, r = divmod(n, 1_000_000_000)
    millions, r = divmod(r, 1_000_000)
    milliers, units = divmod(r, 1000)
    if milliards:
        groups.append(f"{_under_1000(milliards, True)} milliard{'s' if milliards > 1 else ''}")
    if millions:
        groups.append(f"{_under_1000(millions, True)} million{'s' if millions > 1 else ''}")
    if milliers:
        groups.append("mille" if milliers == 1 else f"{_under_1000(milliers, False)} mille")
    if units:
        groups.append(_under_1000(units, True))
    return " ".join(groups)


def amount_in_words(amount) -> str:
    """25000 → 'Vingt-cinq mille dinars algériens seulement.'"""
    amount = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
    dinars, centimes = divmod(int(amount * 100), 100)
    unit = " dinar algérien" if dinars <= 1 else " dinars algériens"
    if dinars >= 1_000_000 and dinars % 1_000_000 == 0:
        unit = " de" + unit
    text = number_to_words_fr(dinars) + unit
    if centimes:
        text += f" et {number_to_words_fr(centimes)} centime{'s' if centimes > 1 else ''}"
    return text[0].upper() + text[1:] + " seulement."


def resolve_period(params):
    """
    Returns (date_from, date_to, label) from GET params.
    Priority: date_from/date_to  >  year[+month]  >  everything.
    """

    def _d(key):
        try:
            return date.fromisoformat(params.get(key) or "")
        except ValueError:
            return None

    d_from, d_to = _d("date_from"), _d("date_to")
    if d_from or d_to:
        label = "Du {} au {}".format(
            d_from.strftime("%d/%m/%Y") if d_from else "…",
            d_to.strftime("%d/%m/%Y") if d_to else "…",
        )
        return d_from, d_to, label
    try:
        year = int(params.get("year") or 0)
    except ValueError:
        year = 0
    try:
        month = int(params.get("month") or 0)
    except ValueError:
        month = 0
    if 1900 <= year <= 2200:
        if 1 <= month <= 12:
            last = calendar.monthrange(year, month)[1]
            return date(year, month, 1), date(year, month, last), f"{MONTHS_FR[month]} {year}"
        return date(year, 1, 1), date(year, 12, 31), f"Année {year}"
    return None, None, "Toutes périodes"


def journal_statement(journal, date_from=None, date_to=None, q=""):
    """
    Chronological statement for the period: opening balance (initial balance
    + everything before date_from), rows with running balance, totals, closing.
    `q` filters displayed rows (designation, beneficiary, notes, reference, amount);
    running balances stay true; match_in/match_out are the totals of matching rows.
    """
    from financial.models import CashVoucher

    def net(qs):
        agg = {
            r["kind"]: r["s"] or Decimal("0")
            for r in qs.values("kind").annotate(s=Sum("amount"))
        }
        return agg.get("in", Decimal("0")), agg.get("out", Decimal("0"))

    qs = journal.vouchers.all()
    opening = journal.initial_balance
    if date_from:
        b_in, b_out = net(qs.filter(date__lt=date_from))
        opening += b_in - b_out
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    needle = " ".join(_fold(q).split())
    balance, rows = opening, []
    total_in = total_out = match_in = match_out = Decimal("0")
    for v in qs.order_by("date", "id"):
        if v.kind == CashVoucher.Kind.IN:
            balance += v.amount
            total_in += v.amount
        else:
            balance -= v.amount
            total_out += v.amount
        if needle:
            hay = _fold(" ".join(
                [v.label, v.counterparty, v.notes, v.reference, f"{v.amount:.2f}",
                 v.date.strftime("%d/%m/%Y")]
            ))
            if not all(w in hay for w in needle.split()):
                continue
        if v.kind == CashVoucher.Kind.IN:
            match_in += v.amount
        else:
            match_out += v.amount
        rows.append({"n": len(rows) + 1, "v": v, "balance": balance})
    return {
        "opening": opening,
        "rows": rows,
        "total_in": total_in,
        "total_out": total_out,
        "match_in": match_in,
        "match_out": match_out,
        "filtered": bool(needle),
        "closing": opening + total_in - total_out,
    }
