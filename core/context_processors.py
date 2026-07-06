# =============================================================================
# core/context_processors.py
# (small companion file — injected into every template context)
# =============================================================================


def institute_info(request):
    """
    Inject the InstituteInfo singleton into every template so headers,
    footers, and printed documents always have access to institute details
    without each view having to fetch it manually.
    """
    from core.models import InstituteInfo

    try:
        info = InstituteInfo.get_instance()
    except Exception:
        info = None
    return {"institute": info}
