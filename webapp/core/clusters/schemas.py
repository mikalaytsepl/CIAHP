from datetime import datetime
from typing import List, Optional

from ninja import Schema


# ── Cluster schemas ──────────────────────────────────────────────────────────

class ClusterIn(Schema):
    name:         str
    cluster_cidr: str = "192.168.0.0/16"
    vip_address:  Optional[str] = None
    kube_version: str = "1.35"


class NodeOut(Schema):
    id:         int
    name:       str
    ip:         str
    role:       str
    status:     str
    created_at: datetime


class ClusterOut(Schema):
    id:           int
    name:         str
    cluster_cidr: str
    vip_address:  Optional[str]
    kube_version: str
    created_at:   datetime
    nodes:        List[NodeOut] = []


class ClusterListOut(Schema):
    id:           int
    name:         str
    cluster_cidr: str
    vip_address:  Optional[str]
    kube_version: str
    created_at:   datetime
    node_count:   int = 0


# ── Node schemas ─────────────────────────────────────────────────────────────

class NodeIn(Schema):
    name:          str
    ip:            str
    role:          str   # "manager" | "worker"
    validate_host: bool = False


class NodeDeployOut(Schema):
    id:           int
    name:         str
    ip:           str
    role:         str
    created_at:   datetime
    operation_id: str


# ── Action input schemas ─────────────────────────────────────────────────────

class DeployManagerIn(Schema):
    kube_version: str = "1.35"


class AddManagerIn(Schema):
    target_node:  Optional[str] = None   # if None, targets all non-[0] managers


class AddWorkerIn(Schema):
    target_node:  Optional[str] = None   # if None, targets all workers in cluster


class DeleteNodeIn(Schema):
    target_node:  str


class HardenIn(Schema):
    target_node:  Optional[str] = None   # if None, hardens entire cluster


class ManageUsersIn(Schema):
    target_node:  Optional[str] = None


class TrivyScanIn(Schema):
    target_node:  str


class SetHaVarsIn(Schema):
    vip_address:    str
    endpoint_port:  int = 8443


class LynisAuditIn(Schema):
    target_node:  str


class NftFwIn(Schema):
    target_node:  Optional[str] = None


class AssociateUserIn(Schema):
    target_user:  str


class DisassociateUserIn(Schema):
    target_user:  str


class BootstrapAnsibleIn(Schema):
    target_node:  Optional[str] = None
    initial_user: str = "root"


# ── Generic action response ──────────────────────────────────────────────────

class ActionOut(Schema):
    operation_id: str
    message:      str = "Playbook dispatched. Poll /api/operations/{operation_id}/ for status."
