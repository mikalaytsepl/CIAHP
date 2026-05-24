"""
Users-list router — read/edit the Ansible `users-list.txt` file from the UI.

The file feeds `manage_users.yml`. Format (one user per line):

    # username, path_to_pub_key, is_admin (true/false)
    admin_tester, ~/.ssh/id_ed25519.pub, true

The file is intentionally git-ignored (contains environment-specific paths),
so GET tolerates a missing file by returning an empty list.
"""

from pathlib import Path
from typing import List

from django.conf import settings
from ninja import Router, Schema
from ninja.errors import HttpError

users_list_router = Router(tags=["Users List"])

_HEADER = "# Format: username, path_to_pub_key, is_admin (true/false)"


def _users_file() -> Path:
    return Path(settings.ANSIBLE_DIR) / "users-list.txt"


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserEntry(Schema):
    name:     str
    key_path: str
    is_admin: bool = False


class UsersListIn(Schema):
    users: List[UserEntry]


# ── Parsing / serialization ─────────────────────────────────────────────────

def _parse(text: str) -> List[dict]:
    users: List[dict] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = [p.strip() for p in s.split(",")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            continue
        users.append({
            "name":     parts[0],
            "key_path": parts[1],
            "is_admin": len(parts) >= 3 and parts[2].lower() == "true",
        })
    return users


# ── Endpoints ─────────────────────────────────────────────────────────────────

@users_list_router.get("/", response=List[UserEntry], summary="Read users-list.txt")
def get_users(request):
    f = _users_file()
    if not f.exists():
        return []
    return _parse(f.read_text(encoding="utf-8"))


@users_list_router.put("/", response=List[UserEntry], summary="Overwrite users-list.txt")
def put_users(request, body: UsersListIn):
    seen = set()
    for u in body.users:
        name = u.name.strip()
        key_path = u.key_path.strip()
        if not name or not key_path:
            raise HttpError(400, "Każdy użytkownik musi mieć nazwę i ścieżkę do klucza.")
        if "," in name or "," in key_path:
            raise HttpError(400, "Nazwa i ścieżka nie mogą zawierać przecinka.")
        if name in seen:
            raise HttpError(400, f"Zduplikowana nazwa użytkownika: {name}")
        seen.add(name)

    lines = [_HEADER]
    for u in body.users:
        lines.append(f"{u.name.strip()}, {u.key_path.strip()}, {str(u.is_admin).lower()}")

    f = _users_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return _parse(f.read_text(encoding="utf-8"))
