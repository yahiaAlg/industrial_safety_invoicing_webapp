from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def da(value, decimals=2):
    """25000 → '25 000,00' (French grouping, comma decimal)."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ""
    s = f"{d:,.{int(decimals)}f}"
    return s.replace(",", " ").replace(".", ",")
