import json
import os
import subprocess
import threading
import time
from pathlib import Path

from django.conf import settings
from django.utils import timezone


def _get_ansible_dir() -> Path:
    return Path(settings.ANSIBLE_DIR)


def _get_tmp_runs_dir() -> Path:
    return _get_ansible_dir() / "tmpruns"


def _to_extra_vars_str(d: dict) -> str:
    """Convert a dict to an ansible --extra-vars JSON string."""
    return json.dumps(d)


def run_playbook(playbook: str, extra_vars: dict, on_success=None, on_failure=None, env=None, inventory=None):
    """
    Spawn an Operation DB record, then run the Ansible playbook in a
    background thread.  Returns the Operation immediately so the caller
    can hand the operation_id back to the HTTP client.

    on_success / on_failure: optional zero-arg callables run in the worker
    thread after the playbook finishes, depending on its exit status. Use
    them for post-run bookkeeping (e.g. removing a wiped node from the DB).

    env: optional dict merged into the ansible-playbook process environment.
    Use it for secrets (e.g. a one-shot password) that must NOT appear in
    --extra-vars, since extra_vars is persisted in the Operation record.
    If "SSHPASS" is present in env, ansible-playbook is run under `sshpass -e`
    for one-time password-based SSH (used by bootstrap).

    inventory: optional string overriding the inventory path passed to ansible
    via `-i`. Use the ad-hoc form `"<ip>,"` to target a host not yet in
    inventory.yml (e.g. bootstrap of a fresh machine).
    """
    # Import here to avoid circular-import issues at module load time
    from operations.models import Operation

    op = Operation.objects.create(playbook=playbook, extra_vars=extra_vars)
    thread = threading.Thread(
        target=_execute,
        args=(op.id, playbook, extra_vars, on_success, on_failure, env, inventory),
        daemon=True,
    )
    thread.start()
    return op


def _execute(op_id, playbook: str, extra_vars: dict, on_success=None, on_failure=None, env=None, inventory=None):
    """Background thread: actually runs ansible-playbook and updates the DB."""
    from operations.models import Operation

    op = Operation.objects.get(id=op_id)
    op.status = Operation.Status.RUNNING
    op.started_at = timezone.now()
    op.save(update_fields=["status", "started_at"])

    ansible_dir = _get_ansible_dir()
    tmp_runs_dir = _get_tmp_runs_dir()
    tmp_runs_dir.mkdir(parents=True, exist_ok=True)
    inventory_arg = inventory if inventory else str(settings.INVENTORY_FILE)
    tmp_marker = tmp_runs_dir / f"instance-{int(time.time())}.tmp"

    # node_id is internal tracking — strip it before passing to ansible-playbook
    node_id = extra_vars.get("node_id")
    ansible_vars = {k: v for k, v in extra_vars.items() if k != "node_id"}

    cmd = [
        "ansible-playbook",
        str(ansible_dir / "playbooks" / playbook),
        "-i", inventory_arg,
    ]

    if ansible_vars:
        cmd += ["--extra-vars", _to_extra_vars_str(ansible_vars)]

    run_env = None
    conn_pass_file = None
    become_pass_file = None
    if env:
        import os, tempfile
        run_env = {**os.environ, **env}
        # SSHPASS in env → bootstrap with password SSH auth. We CAN'T just wrap
        # `sshpass -e ansible-playbook …` externally: ansible spawns ssh without
        # a TTY, so the password prompt never reaches sshpass. Instead use
        # ansible's native --connection-password-file (it invokes sshpass
        # correctly internally) plus --become-password-file (assume sudo pass ==
        # ssh pass — typical for the "existing admin" case). Both files are
        # mode 0600 and removed in `finally`, so the password never lands in
        # argv, --extra-vars, inventory, or the Operation log.
        if "SSHPASS" in env:
            password_bytes = env["SSHPASS"].encode()

            fd, conn_pass_file = tempfile.mkstemp(prefix="ciahp_conn_")
            try:
                os.write(fd, password_bytes)
            finally:
                os.close(fd)
            os.chmod(conn_pass_file, 0o600)
            cmd += [f"--connection-password-file={conn_pass_file}"]

            fd, become_pass_file = tempfile.mkstemp(prefix="ciahp_become_")
            try:
                os.write(fd, password_bytes)
            finally:
                os.close(fd)
            os.chmod(become_pass_file, 0o600)
            cmd += [f"--become-password-file={become_pass_file}"]

            # Force password-only auth so ssh doesn't waste attempts on the
            # global `ansible` key (which initial_user doesn't accept yet).
            cmd += ["--ssh-extra-args=-o PreferredAuthentications=password -o PubkeyAuthentication=no"]

    try:
        tmp_marker.write_text(
            json.dumps(
                {
                    "operation_id": str(op.id),
                    "playbook": playbook,
                    "inventory": inventory_arg,
                    "started_at": timezone.now().isoformat(),
                    "extra_vars": ansible_vars,
                    "command": cmd,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(ansible_dir),
            env=run_env,
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
        try:
            tmp_marker.write_text(
                json.dumps(
                    {
                        "operation_id": str(op.id),
                        "playbook": playbook,
                        "inventory": inventory_arg,
                        "started_at": timezone.now().isoformat(),
                        "extra_vars": ansible_vars,
                        "error": str(exc),
                        "command": cmd,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass
    finally:
        for _f in (conn_pass_file, become_pass_file):
            if _f:
                try:
                    os.unlink(_f)
                except Exception:
                    pass

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

    if op.status == Operation.Status.SUCCESS:
        try:
            tmp_marker.unlink()
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[runner] failed to remove tmp marker {tmp_marker}: {e}")
