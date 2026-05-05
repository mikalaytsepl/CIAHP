"""
Inventory router — read/inspect the Ansible inventory file directly.

Useful for debugging the YAML state without opening the server filesystem.
"""

from ninja import Router
from django.conf import settings

inventory_router = Router(tags=["Inventory"])


def _get_manager():
    import sys
    from pathlib import Path

    scripts_dir = Path(settings.BASE_DIR).parent.parent / "scripts" / "integration_scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from inventory_manager import InventoryManager  # noqa: PLC0415
    return InventoryManager(str(settings.INVENTORY_FILE))


@inventory_router.get("/", summary="Return the current Ansible inventory as JSON")
def get_inventory(request):
    """
    Reads the raw inventory.yml and returns it parsed as JSON.
    This is a read-only snapshot — mutations go through /api/clusters/.
    """
    mgr = _get_manager()
    return mgr._load()


@inventory_router.get("/clusters/", summary="List cluster names present in inventory")
def list_inventory_clusters(request):
    mgr = _get_manager()
    inv = mgr._load()
    try:
        cluster_names = list(inv["all"]["children"]["clusters"]["children"].keys())
    except (KeyError, TypeError):
        cluster_names = []
    return {"clusters": cluster_names}
