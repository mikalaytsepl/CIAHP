from ninja import NinjaAPI

from clusters.router import clusters_router
from operations.router import operations_router
from inventory.router import inventory_router

api = NinjaAPI(
    title="CIAHP API",
    version="1.0",
    description=(
        "Cluster Infrastructure Automation & Hardening Platform. "
        "Manage Kubernetes clusters via Ansible playbooks."
    ),
)

api.add_router("/clusters/",   clusters_router)
api.add_router("/operations/", operations_router)
api.add_router("/inventory/",  inventory_router)


@api.get("/health", tags=["Health"], summary="Health check")
def health(request):
    return {"status": "ok"}