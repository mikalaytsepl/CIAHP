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


def run_playbook(playbook: str, extra_vars: dict):
    """
    Spawn an Operation DB record, then run the Ansible playbook in a
    background thread.  Returns the Operation immediately so the caller
    can hand the operation_id back to the HTTP client.
    """
    # Import here to avoid circular-import issues at module load time
    from operations.models import Operation

    op = Operation.objects.create(playbook=playbook, extra_vars=extra_vars)
    thread = threading.Thread(target=_execute, args=(op.id, playbook, extra_vars), daemon=True)
    thread.start()
    return op


def _execute(op_id, playbook: str, extra_vars: dict):
    """Background thread: actually runs ansible-playbook and updates the DB."""
    from operations.models import Operation

    op = Operation.objects.get(id=op_id)
    op.status = Operation.Status.RUNNING
    op.started_at = timezone.now()
    op.save(update_fields=["status", "started_at"])

    ansible_dir = _get_ansible_dir()
    inventory_file = Path(settings.INVENTORY_FILE)

    cmd = [
        "ansible-playbook",
        str(ansible_dir / "playbooks" / playbook),
        "-i", str(inventory_file),
    ]

    if extra_vars:
        cmd += ["--extra-vars", _to_extra_vars_str(extra_vars)]

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
