"""
Service layer for Cluster & Node management.

Responsibilities:
  - Keep the Django DB (Cluster / Node) in sync with the Ansible inventory file.
  - Provide helper methods used by the Ninja router to avoid fat controller code.
"""

from django.conf import settings

from .models import Cluster, Node
from operations.models import Operation


def _get_inventory_manager():
    """Return a fresh InventoryManager pointed at the configured inventory file."""
    import sys
    from pathlib import Path

    scripts_dir = Path(settings.BASE_DIR).parent.parent / "scripts" / "integration_scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from inventory_manager import InventoryManager  # noqa: PLC0415
    return InventoryManager(str(settings.INVENTORY_FILE))


# ── Cluster helpers ──────────────────────────────────────────────────────────

def create_cluster(name: str, cluster_cidr: str, vip_address: str | None, kube_version: str) -> Cluster:
    cluster = Cluster.objects.create(
        name=name,
        cluster_cidr=cluster_cidr,
        vip_address=vip_address,
        kube_version=kube_version,
    )
    if vip_address:
        mgr = _get_inventory_manager()
        mgr.set_cluster_ha_vars(cluster_name=name, vip_address=vip_address)
    Operation.objects.create(
        playbook="create-cluster",
        extra_vars={"target_cluster": name, "cluster_cidr": cluster_cidr},
        status=Operation.Status.SUCCESS,
    )
    return cluster


def delete_cluster_record(cluster: Cluster) -> None:
    """Remove from DB only — actual node cleanup is done by the delete_cluster playbook."""
    inv_mgr = _get_inventory_manager()
    try:
        inv_mgr.truncate_cluster_resources(cluster.name)
    except Exception:
        pass  # Inventory may already be empty; proceed with DB delete
    Operation.objects.create(
        playbook="delete-cluster",
        extra_vars={"target_cluster": cluster.name},
        status=Operation.Status.SUCCESS,
    )
    cluster.delete()


# ── Node helpers ─────────────────────────────────────────────────────────────

def add_node(cluster: Cluster, name: str, ip: str, role: str, validate_host: bool = False) -> Node:
    """
    Add a node to the Ansible inventory (with validation) and persist to DB.
    role must be 'manager' or 'worker'.
    """
    ansible_role = "managers" if role == "manager" else "workers"
    mgr = _get_inventory_manager()
    final_name = mgr.add_host(name=name, ip=ip, cluster_name=cluster.name, role=ansible_role, validate=validate_host)

    node = Node.objects.create(
        cluster=cluster,
        name=final_name,
        ip=ip,
        role=role,
    )
    Operation.objects.create(
        playbook="add-node",
        extra_vars={"target_cluster": cluster.name, "node": node.name, "ip": ip, "role": role},
        status=Operation.Status.SUCCESS,
    )
    return node


def remove_node(cluster: Cluster, node: Node) -> None:
    """Remove a node from inventory and DB."""
    ansible_role = "managers" if node.role == "manager" else "workers"
    mgr = _get_inventory_manager()
    try:
        mgr.delete_host(name=node.name, cluster_name=cluster.name, role=ansible_role)
    except ValueError:
        pass  # Host may have been manually removed from inventory; proceed
    Operation.objects.create(
        playbook="remove-node",
        extra_vars={"target_cluster": cluster.name, "node": node.name, "role": node.role},
        status=Operation.Status.SUCCESS,
    )
    node.delete()
