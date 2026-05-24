from django.contrib.auth.decorators import login_required
from ninja import NinjaAPI
from ninja.security import django_auth

from clusters.router import clusters_router
from operations.router import operations_router
from inventory.router import inventory_router
from api.users_list import users_list_router

# django_auth = authenticated Django session. Browser fetch() calls carry the
# session cookie + X-CSRFToken header (already sent by the frontend JS), so the
# UI keeps working; unauthenticated callers get 401.
# docs_decorator also gates the Swagger UI (/api/docs) and the OpenAPI schema
# (/api/openapi.json) behind login — otherwise the schema is world-readable.
api = NinjaAPI(
    title="CIAHP API",
    version="1.0",
    description=(
        "Cluster Infrastructure Automation & Hardening Platform. "
        "Manage Kubernetes clusters via Ansible playbooks."
    ),
    auth=django_auth,
    docs_decorator=login_required,
)

api.add_router("/clusters/",   clusters_router)
api.add_router("/operations/", operations_router)
api.add_router("/inventory/",  inventory_router)
api.add_router("/users-list/", users_list_router)


@api.get("/health", tags=["Health"], summary="Health check", auth=None)
def health(request):
    return {"status": "ok"}