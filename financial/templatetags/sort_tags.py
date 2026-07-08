# =============================================================================
# financial/templatetags/sort_tags.py
# =============================================================================
"""
{% sort_th "field_key" "Label" %} renders a clickable column header used by
sortable list tables (invoice_list, expense_list, …), the same pattern as the
formations catalogue: click a header to sort by it, click again to flip
direction. All other querystring params (filters, page) are preserved except
'page', which is dropped since sorting resets pagination to page 1.

The view is responsible for whitelisting which "field_key" values are valid
via financial.utils.apply_sorting — this tag only reflects request.GET, it
never touches the ORM.
"""

from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag(takes_context=True)
def sort_th(context, field, label, align="left"):
    request = context["request"]
    current_sort = request.GET.get("sort", "")
    current_dir = request.GET.get("dir", "asc")
    is_active = current_sort == field
    next_dir = "desc" if (is_active and current_dir == "asc") else "asc"

    params = request.GET.copy()
    params["sort"] = field
    params["dir"] = next_dir
    params.pop("page", None)
    url = "?" + params.urlencode()

    justify = {"right": "flex-end", "center": "center"}.get(align, "flex-start")

    if is_active:
        icon = "bi-caret-up-fill" if current_dir == "asc" else "bi-caret-down-fill"
        return format_html(
            '<a href="{}" style="display:inline-flex;align-items:center;gap:5px;'
            "justify-content:{};color:var(--accent);font-weight:700;"
            'text-decoration:none;width:100%;">{}'
            '<i class="bi {}" style="font-size:10px;"></i></a>',
            url,
            justify,
            label,
            icon,
        )

    return format_html(
        '<a href="{}" style="display:inline-flex;align-items:center;gap:5px;'
        'justify-content:{};color:inherit;text-decoration:none;width:100%;">'
        '{}<i class="bi bi-arrow-down-up" style="font-size:9px;opacity:.25;"></i></a>',
        url,
        justify,
        label,
    )
