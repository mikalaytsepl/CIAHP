import json
import subprocess
import threading
from pathlib import Path

from django.conf import settings
from django.utils import timezone


def _get_ansible_dir() -> Path:
    return Path(settings.ANSIBLE_DIR)


def _to_extra_vars_str(d: dict) -> str:
    """Convert a dict to an ansible --extra-vars JSON string."""
    return json.dumps(d)


def run_playbook(playbook: str, extra_vars: dict, on_success=None, on_failure=None):
    """
    Spawn an Operation DB record, then run the Ansible playbook in a
    background thread.  Returns the Operation immediately so the caller
    can hand the operation_id back to the HTTP client.

    on_success / on_failure: optional zero-arg callables run in the worker
    thread after the playbook finishes, depending on its exit status. Use
    them for post-run bookkeeping (e.g. removing a wiped node from the DB).
    """
    # Import here to avoid circular-import issues at module load time
    from operations.models import Operation

    op = Operation.objects.create(playbook=playbook, extra_vars=extra_vars)
    thread = threading.Thread(
        target=_execute,
        args=(op.id, playbook, extra_vars, on_success, on_failure),
        daemon=True,
    )
    thread.start()
    return op


def _execute(op_id, playbook: str, extra_vars: dict, on_success=None, on_failure=None):
    """Background thread: actually runs ansible-playbook and updates the DB."""
    from operations.models import Operation

    op = Operation.objects.get(id=op_id)
    op.status = Operation.Status.RUNNING
    op.started_at = timezone.now()
    op.save(update_fields=["status", "started_at"])

    ansible_dir = _get_ansible_dir()
    inventory_file = Path(settings.INVENTORY_FILE)

    # node_id is internal tracking — strip it before passing to ansible-playbook
    node_id = extra_vars.get("node_id")
    ansible_vars = {k: v for k, v in extra_vars.items() if k != "node_id"}

    cmd = [
        "ansible-playbook",
        str(ansible_dir / "playbooks" / playbook),
        "-i", str(inventory_file),
    ]

    if ansible_vars:
        cmd += ["--extra-vars", _to_extra_vars_str(ansible_vars)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(ansible_dir),
        )
        op.stdout = result.stdout
        op.stderr = result.stderr
        op.return_code = result.returncode
        op.status = (
            Operation.Status.SUCCESS if result.returncode == 0 else Operation.Status.FAILED
        )
    except Exception as exc:
        op.stderr = str(exc)
        op.return_code = -1
        op.status = Operation.Status.FAILED

    op.finished_at = timezone.now()
    op.save(update_fields=["stdout", "stderr", "return_code", "status", "finished_at"])

    # Update the node's status to reflect the playbook result
    if node_id:
        from django.db import close_old_connections
        close_old_connections()
        try:
            from clusters.models import Node
            node_obj = Node.objects.get(id=int(node_id))
            node_obj.status = (
                Node.Status.HEALTHY if op.status == Operation.Status.SUCCESS
                else Node.Status.ERROR
            )
            node_obj.save(update_fields=["status"])
        except Exception as e:
            print(f"[runner] Failed to update node {node_id} status: {e}")

    # Run the caller's completion hook (e.g. purge a wiped node/cluster)
    callback = on_success if op.status == Operation.Status.SUCCESS else on_failure
    if callback is not None:
        from django.db import close_old_connections
        close_old_connections()
        try:
            callback()
        except Exception as e:
            print(f"[runner] completion callback failed for op {op_id}: {e}")
