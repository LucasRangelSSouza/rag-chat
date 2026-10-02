"""Creates the read-only demo login in the public Metabase and puts it in the "Portfolio viewers" group.

Run it yourself on the VPS (it asks for the password on the terminal; nothing is stored or printed):
  bash /opt/rag-chat-infra/metabase_demo_user.sh user@rangeltech.net
"""
import getpass
import os
import sys

sys.path.insert(0, "/seed")
from seed_dashboards import Metabase, env, wait_healthy  # noqa: E402

GROUP = "Portfolio viewers"


def main(email: str) -> None:
    password = os.environ.get("DEMO_PASSWORD")  # non-interactive runs; otherwise ask on the terminal
    if not password:
        password = getpass.getpass(f"Password for {email}: ")
        if password != getpass.getpass("Repeat it: "):
            raise SystemExit("passwords differ")
    mb = Metabase(env("MB_URL"))
    wait_healthy(mb)
    mb.session = mb.call("POST", "/api/session", {"username": env("METABASE_ADMIN_EMAIL"),
                                                  "password": env("METABASE_ADMIN_PASSWORD")})["id"]
    group = next(g for g in mb.call("GET", "/api/permissions/group") if g["name"] == GROUP)
    users = mb.call("GET", "/api/user?status=all")
    users = users["data"] if isinstance(users, dict) else users
    existing = next((u for u in users if u["email"].lower() == email.lower()), None)
    body = {"first_name": "Portfolio", "last_name": "Demo", "email": email}
    if existing:
        user = mb.call("PUT", f"/api/user/{existing['id']}", {**body, "is_active": True})
    else:
        user = mb.call("POST", "/api/user", body)
    members = mb.call("GET", "/api/permissions/membership")
    mine = members.get(str(user["id"])) or members.get(user["id"]) or []
    if not any(m["group_id"] == group["id"] for m in mine):  # joined through the membership API: the user-create call refuses group lists on this version
        mb.call("POST", "/api/permissions/membership", {"group_id": group["id"], "user_id": user["id"]})
    mb.call("PUT", f"/api/user/{user['id']}/password", {"password": password})
    print(f"ready: {email} in group '{GROUP}' (read-only)")


if __name__ == "__main__":
    main(sys.argv[1])
