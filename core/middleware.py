"""
Middleware to support running this app behind an nginx reverse proxy
at a subpath (e.g. /facturation/), as configured in the shared server's
nginx config:

    location /facturation/ {
        proxy_pass ...;
        proxy_set_header SCRIPT_NAME /facturation;
    }

Nginx's proxy_set_header only adds an HTTP header (arrives as
HTTP_SCRIPT_NAME in the WSGI environ) — it does NOT populate WSGI's
SCRIPT_NAME on its own. Without this middleware, Django would see
PATH_INFO like "/facturation/clients/" which doesn't match any URL
pattern in urls.py (which has no /facturation/ prefix), causing 404s.
This middleware:
  1. Reads the forwarded SCRIPT_NAME header.
  2. Strips that prefix from PATH_INFO so URL resolution works normally.
  3. Sets environ['SCRIPT_NAME'] so Django's reverse()/{% url %} and
     request.build_absolute_uri() correctly re-add the /facturation
     prefix when generating links.
"""


class ScriptNameFromHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        script_name = request.META.get("HTTP_SCRIPT_NAME", "")
        if script_name:
            request.META["SCRIPT_NAME"] = script_name
            if request.path_info.startswith(script_name):
                request.path_info = request.path_info[len(script_name) :] or "/"
        return self.get_response(request)
