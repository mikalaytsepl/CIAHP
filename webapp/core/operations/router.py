import uuid
from typing import List, Optional

from ninja import Router
from django.shortcuts import get_object_or_404

from .models import Operation
from .schemas import OperationOut, OperationListOut

operations_router = Router(tags=["Operations"])


@operations_router.get("/", response=List[OperationListOut], summary="List all operations")
def list_operations(request, status: Optional[str] = None, playbook: Optional[str] = None):
    """Return all operations, optionally filtered by status and/or playbook name."""
    qs = Operation.objects.all()
    if status:
        qs = qs.filter(status=status)
    if playbook:
        qs = qs.filter(playbook__icontains=playbook)
    return list(qs)


@operations_router.get("/{op_id}/", response=OperationOut, summary="Get operation detail")
def get_operation(request, op_id: uuid.UUID):
    """Return full detail of a single operation including stdout/stderr."""
    op = get_object_or_404(Operation, id=op_id)
    return op
