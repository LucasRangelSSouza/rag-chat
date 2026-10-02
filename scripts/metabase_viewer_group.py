"""Creates (or updates) a read-only "Portfolio viewers" group in the public Metabase.

The group can open the dashboards in the root collection and browse the public tables with the query builder
(see table names, fields and rows). It cannot write native SQL, edit anything or reach admin settings. People are
added to the group by an admin in Metabase; this script never creates users or passwords.

Runs on the VPS with the same environment as seed/run_seed.sh:
  MB_URL, METABASE_ADMIN_EMAIL, METABASE_ADMIN_PASSWORD
Prints the database id and the browse links for the chat's base cards.
"""
import json
import os
import sys

sys.path.insert(0, "/seed")
from seed_dashboards import DB_NAME, Metabase, env, wait_healthy  # noqa: E402

GROUP = "Portfolio viewers"
SCHEMAS = ["pncp", "siope", "ibge", "bi"]


def main() -> None:
    mb = Metabase(env("MB_URL"))
    wait_healthy(mb)
    mb.session = mb.call("POST", "/api/session", {"username": env("METABASE_ADMIN_EMAIL"),
                                                  "password": env("METABASE_ADMIN_PASSWORD")})["id"]
    listing = mb.call("GET", "/api/database")
    databases = listing["data"] if isinstance(listing, dict) else listing
    db_id = next(db["id"] for db in databases if db["name"] == DB_NAME)

    groups = mb.call("GET", "/api/permissions/group")
    group = next((g for g in groups if g["name"] == GROUP), None) or mb.call("POST", "/api/permissions/group", {"name": GROUP})
    gid = group["id"]

    graph = mb.call("GET", "/api/permissions/graph")
    graph["groups"][str(gid)] = {
        str(other["id"]): {"view-data": "unrestricted", "create-queries": "no"} for other in databases}
    graph["groups"][str(gid)][str(db_id)] = {
        "view-data": "unrestricted",
        "create-queries": {schema: "query-builder" for schema in SCHEMAS},
    }
    # Every user is also in "All Users", whose grants add to any group's. Close it down so the viewer group alone
    # decides what a demo login sees; administrators bypass group permissions, so they are unaffected.
    all_users = next(g["id"] for g in groups if g["name"] == "All Users")
    graph["groups"][str(all_users)] = {str(db["id"]): {"view-data": "unrestricted", "create-queries": "no"} for db in databases}
    mb.call("PUT", "/api/permissions/graph", {"groups": {str(gid): graph["groups"][str(gid)],
                                                         str(all_users): graph["groups"][str(all_users)]},
                                              "revision": graph["revision"]})

    collections = mb.call("GET", "/api/collection/graph")
    collections["groups"].setdefault(str(gid), {})["root"] = "read"
    collections["groups"].setdefault(str(all_users), {})["root"] = "none"
    mb.call("PUT", "/api/collection/graph", {"groups": {str(gid): collections["groups"][str(gid)],
                                                        str(all_users): collections["groups"][str(all_users)]},
                                             "revision": collections["revision"]})

    base = os.environ.get("PUBLIC_MB_URL", "https://bi.rangeltech.net").rstrip("/")
    print(json.dumps({"group_id": gid, "database_id": db_id,
                      "browse": {schema: f"{base}/browse/databases/{db_id}/schema/{schema}" for schema in SCHEMAS}}, indent=1))


if __name__ == "__main__":
    main()
