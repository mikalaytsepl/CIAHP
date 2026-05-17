"""
Ninja router for Cluster, Node, and Action endpoints.

URL layout (all prefixed with /api/clusters/ in api.py):

  GET    /                                  → list clusters
  POST   /                                  → create cluster
  GET    /{cluster_name}/                   → cluster detail + nodes
  DELETE /{cluster_name}/                   → delete cluster record

  GET    /{cluster_name}/nodes/             → list nodes
  POST   /{cluster_name}/nodes/             → add node (writes to inventory)
  DELETE /{cluster_name}/nodes/{node_name}/ → remove node from inventory

  POST   /{cluster_name}/actions/deploy-manager        → bootstrap first manager
  POST   /{cluster_name}/actions/add-manager           → join additional manager
  POST   /{cluster_name}/actions/add-worker            → join worker node(s)
  POST   /{cluster_name}/actions/delete-node           → drain & wipe a node
  POST   /{cluster_name}/actions/delete-cluster        → wipe entire cluster
  POST   /{cluster_name}/actions/harden                → security hardening
  POST   /{cluster_name}/actions/manage-users          → push SSH users
  POST   /{cluster_name}/actions/scan-trivy            → Trivy vulnerability scan
  POST   /{cluster_name}/actions/set-ha-vars           → write VIP/endpoint to inventory
"""

from typing import List

from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from runner.ansible_runner import run_playbook

from .models import Cluster, Node
from .schemas import (
    ActionOut,
    AddManagerIn,
    AddWorkerIn,
    ClusterIn,
    ClusterListOut,
    ClusterOut,
    DeleteNodeIn,
    DeployManagerIn,
    HardenIn,
    ManageUsersIn,
    NodeDeployOut,
    NodeIn,
    NodeOut,
    SetHaVarsIn,
    TrivyScanIn,
)
from .services import add_node, create_cluster, delete_cluster_record, remove_node

clusters_router = Router(tags=["Clusters"])


# ── Cluster CRUD ─────────────────────────────────────────────────────────────

@clusters_router.get("/", response=List[ClusterListOut], summary="List clusters")
def list_clusters(request):
    clusters = Cluster.objects.prefetch_related("nodes").all()
    result = []
    for c in clusters:
        result.append(
            ClusterListOut(
                id=c.id,
                name=c.name,
                cluster_cidr=c.cluster_cidr,
                vip_address=c.vip_address,
                kube_version=c.kube_version,
                created_at=c.created_at,
                node_count=c.nodes.count(),
            )
        )
    return result


@clusters_router.post("/", response=ClusterOut, summary="Create cluster")
def create_cluster_endpoint(request, body: ClusterIn):
    if Cluster.objects.filter(name=body.name).exists():
        raise HttpError(409, f"Cluster '{body.name}' already exists.")
    cluster = create_cluster(
        name=body.name,
        cluster_cidr=body.cluster_cidr,
        vip_address=body.vip_address,
        kube_version=body.kube_version,
    )
    return _cluster_out(cluster)


@clusters_router.get("/{cluster_name}/", response=ClusterOut, summary="Get cluster detail")
def get_cluster(request, cluster_name: str):
    cluster = get_object_or_404(Cluster, name=cluster_name)
    return _cluster_out(cluster)


@clusters_router.delete("/{cluster_name}/", response={204: None}, summary="Delete cluster record")
def delete_cluster_endpoint(request, cluster_name: str):
    cluster = get_object_or_404(Cluster, name=cluster_name)
    delete_cluster_record(cluster)
    return 204, None


# ── Node CRUD ────────────────────────────────────────────────────────────────

@clusters_router.get("/{cluster_name}/nodes/", response=List[NodeOut], summary="List nodes")
def list_nodes(request, cluster_name: str):
    cluster = get_object_or_404(Cluster, name=cluster_name)
    return list(cluster.nodes.all())


@clusters_router.post("/{cluster_name}/nodes/", response=NodeDeployOut, summary="Add node to cluster and deploy")
def add_node_endpoint(request, cluster_name: str, body: NodeIn):
    cluster = get_object_or_404(Cluster, name=cluster_name)
    if body.role not in ("manager", "worker"):
        raise HttpError(400, "role must be 'manager' or 'worker'.")
    try:
        node = add_node(cluster=cluster, name=body.name, ip=body.ip, role=body.role)
    except ValueError as e:
        raise HttpError(400, str(e))

    # Trigger the appropriate playbook immediately after registering the node
    if node.role == "manager":
        existing_managers = cluster.nodes.filter(role="manager").exclude(id=node.id).count()
        if existing_managers == 0:
            op = run_playbook("deploy_main_manager.yml", {
                "target_cluster": cluster_name,
                "cluster_cidr":   cluster.cluster_cidr,
                "kube_version":   cluster.kube_version,
                "node_id":        node.id,
            })
        else:
            op = run_playbook("deploy_additional_manager.yml", {
                "target_cluster": cluster_name,
                "target_node":    node.name,
                "node_id":        node.id,
            })
    else:
        op = run_playbook("deploy_worker.yml", {
            "target_cluster": cluster_name,
            "target_node":    node.name,
            "node_id":        node.id,
        })

    return NodeDeployOut(
        id=node.id, name=node.name, ip=node.ip,
        role=node.role, created_at=node.created_at,
        operation_id=str(op.id),
    )


@clusters_router.delete(
    "/{cluster_name}/nodes/{node_name}/",
    response={204: None},
    summary="Remove node from cluster inventory",
)
def remove_node_endpoint(request, cluster_name: str, node_name: str):
    cluster = get_object_or_404(Cluster, name=cluster_name)
    node = get_object_or_404(Node, cluster=cluster, name=node_name)
    remove_node(cluster=cluster, node=node)
    return 204, None


# ── Actions ──────────────────────────────────────────────────────────────────

@clusters_router.post(
    "/{cluster_name}/actions/deploy-manager",
    response=ActionOut,
    summary="Bootstrap the first Kubernetes manager (control plane)",
)
def action_deploy_manager(request, cluster_name: str, body: DeployManagerIn):
    _require_cluster(cluster_name)
    op = run_playbook(
        "deploy_main_manager.yml",
        {
            "target_cluster": cluster_name,
            "cluster_cidr":   _get_cluster_cidr(cluster_name),
            "kube_version":   body.kube_version,
        },
    )
    return ActionOut(operation_id=str(op.id))


@clusters_router.post(
    "/{cluster_name}/actions/add-manager",
    response=ActionOut,
    summary="Join an additional control-plane manager to an existing cluster",
)
def action_add_manager(request, cluster_name: str, body: AddManagerIn):
    _require_cluster(cluster_name)
    extra: dict = {"target_cluster": cluster_name}
    if body.target_node:
        extra["target_node"] = body.target_node
    op = run_playbook("deploy_additional_manager.yml", extra)
    return ActionOut(operation_id=str(op.id))


@clusters_router.post(
    "/{cluster_name}/actions/add-worker",
    response=ActionOut,
    summary="Join worker node(s) to a cluster",
)
def action_add_worker(request, cluster_name: str, body: AddWorkerIn):
    _require_cluster(cluster_name)
    extra: dict = {"target_cluster": cluster_name}
    if body.target_node:
        extra["target_node"] = body.target_node
    op = run_playbook("deploy_worker.yml", extra)
    return ActionOut(operation_id=str(op.id))


@clusters_router.post(
    "/{cluster_name}/actions/delete-node",
    response=ActionOut,
    summary="Drain and wipe a single node from the cluster",
)
def action_delete_node(request, cluster_name: str, body: DeleteNodeIn):
    _require_cluster(cluster_name)
    op = run_playbook(
        "delete_node.yml",
        {"target_cluster": cluster_name, "target_node": body.target_node},
    )
    return ActionOut(operation_id=str(op.id))


@clusters_router.post(
    "/{cluster_name}/actions/delete-cluster",
    response=ActionOut,
    summary="Wipe all nodes in a cluster (no graceful drain)",
)
def action_delete_cluster(request, cluster_name: str):
    _require_cluster(cluster_name)
    op = run_playbook("delete_cluster.yml", {"target_cluster": cluster_name})
    return ActionOut(operation_id=str(op.id))


@clusters_router.post(
    "/{cluster_name}/actions/harden",
    response=ActionOut,
    summary="Apply security hardening tasks",
)
def action_harden(request, cluster_name: str, body: HardenIn):
    _require_cluster(cluster_name)
    extra: dict = {"target_cluster": cluster_name}
    if body.target_node:
        extra["target_node"] = body.target_node
    op = run_playbook("node_hardening.yml", extra)
    return ActionOut(operation_id=str(op.id))


@clusters_router.post(
    "/{cluster_name}/actions/manage-users",
    response=ActionOut,
    summary="Push SSH user accounts to nodes",
)
def action_manage_users(request, cluster_name: str, body: ManageUsersIn):
    _require_cluster(cluster_name)
    extra: dict = {"target_cluster": cluster_name}
    if body.target_node:
        extra["target_node"] = body.target_node
    op = run_playbook("manage_users.yml", extra)
    return ActionOut(operation_id=str(op.id))


@clusters_router.post(
    "/{cluster_name}/actions/scan-trivy",
    response=ActionOut,
    summary="Install Trivy and run a vulnerability scan on a node",
)
def action_scan_trivy(request, cluster_name: str, body: TrivyScanIn):
    _require_cluster(cluster_name)
    op = run_playbook(
        "trivy_provisioning.yml",
        {"target_cluster": cluster_name, "target_node": body.target_node},
    )
    return ActionOut(operation_id=str(op.id))


@clusters_router.post(
    "/{cluster_name}/actions/set-ha-vars",
    response=ActionOut,
    summary="Write VIP address and control-plane endpoint into the inventory",
)
def action_set_ha_vars(request, cluster_name: str, body: SetHaVarsIn):
    cluster = get_object_or_404(Cluster, name=cluster_name)
    # Update inventory file via InventoryManager
    from clusters.services import _get_inventory_manager  # noqa: PLC0415
    mgr = _get_inventory_manager()
    mgr.set_cluster_ha_vars(
        cluster_name=cluster_name,
        vip_address=body.vip_address,
        endpoint_port=body.endpoint_port,
    )
    # Persist to DB
    cluster.vip_address = body.vip_address
    cluster.save(update_fields=["vip_address"])
    # Return a synthetic operation (no playbook run needed)
    from operations.models import Operation  # noqa: PLC0415
    import uuid
    op = Operation.objects.create(
        playbook="set-ha-vars (inventory only)",
        extra_vars={"vip_address": body.vip_address, "endpoint_port": body.endpoint_port},
        status=Operation.Status.SUCCESS,
    )
    return ActionOut(operation_id=str(op.id), message="HA vars written to inventory.")


# ── Private helpers ──────────────────────────────────────────────────────────

def _require_cluster(cluster_name: str) -> Cluster:
    return get_object_or_404(Cluster, name=cluster_name)


def _get_cluster_cidr(cluster_name: str) -> str:
    cluster = Cluster.objects.get(name=cluster_name)
    return cluster.cluster_cidr


def _cluster_out(cluster: Cluster) -> ClusterOut:
    return ClusterOut(
        id=cluster.id,
        name=cluster.name,
        cluster_cidr=cluster.cluster_cidr,
        vip_address=cluster.vip_address,
        kube_version=cluster.kube_version,
        created_at=cluster.created_at,
        nodes=[
            NodeOut(
                id=n.id,
                name=n.name,
                ip=n.ip,
                role=n.role,
                created_at=n.created_at,
            )
            for n in cluster.nodes.all()
        ],
    )
