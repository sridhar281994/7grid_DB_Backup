#!/usr/bin/env python3
"""
Unified Rubrik CDM backup checker for filesets and VM snapshots.

Features
--------
- Single authentication and GraphQL client for both checks
- Checks only today's or yesterday's snapshots (UTC-aware)
- Supports optional proxy configuration
- Provides separate JSON artifacts for fileset and VM snapshot checks
- Saves a full fileset dump for audit/debug parity with prior tooling
- Includes snapshot counts and SLA domain names per server

Environment variables
---------------------
RSC_FQDN                     Rubrik Security Cloud (CDM) FQDN (default: kohls.my.rubrik.com)
RUBRIK_CLIENT_ID             OAuth client id for CDM
RUBRIK_CLIENT_SECRET         OAuth client secret for CDM
HTTP_PROXY / HTTPS_PROXY     Optional proxy endpoints
SERVER_LIST_PATH             Path to the shared server list file
serverlist                   Alternate env var name for SERVER_LIST_PATH (GitLab compatibility)
FILESET_SERVER_LIST_PATH     Optional override path for fileset-specific server list
VMSNAPSHOT_SERVER_LIST_PATH  Optional override path for VM snapshot server list
ALL_FILESETS_DUMP            Output path for full fileset dump (default: L2Backup/all_filesets_dump.json)
FILESET_OUT_FILE             Output JSON for fileset results (default: L2Backup/partial_results_check_filesets.json)
SNAPSHOT_OUT_FILE            Output JSON for VM snapshot results (default: L2Backup/partial_results_<job>.json)
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests

import gpls

# Disable TLS warnings for self-signed Rubrik clusters
requests.packages.urllib3.disable_warnings()


# ==========================================
# CONFIGURATION
# ==========================================
RSC_FQDN = os.getenv("RSC_FQDN", "kohls.my.rubrik.com")
CID = os.getenv("RUBRIK_CLIENT_ID")
CSECRET = os.getenv("RUBRIK_CLIENT_SECRET")
PROXY = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
PROXIES = {"http": PROXY, "https": PROXY} if PROXY else None
REQUEST_TIMEOUT = int(os.getenv("RUBRIK_REQUEST_TIMEOUT", "10"))

SERVER_LIST_PATH = os.getenv("SERVER_LIST_PATH") or os.getenv("serverlist")
FILESET_SERVER_LIST_PATH = os.getenv("FILESET_SERVER_LIST_PATH")
VMSNAPSHOT_SERVER_LIST_PATH = os.getenv("VMSNAPSHOT_SERVER_LIST_PATH")

ALL_FILESETS_DUMP = os.getenv("ALL_FILESETS_DUMP", "L2Backup/all_filesets_dump.json")
FILESET_OUT_FILE = os.getenv("FILESET_OUT_FILE", "L2Backup/partial_results_check_filesets.json")
job_id = os.getenv("CI_JOB_NAME", "default").replace(" ", "_")
SNAPSHOT_OUT_FILE = os.getenv("SNAPSHOT_OUT_FILE", f"L2Backup/partial_results_{job_id}.json")


# ==========================================
# Rubrik GraphQL Client
# ==========================================
class Rubrik:
    def __init__(self, fqdn: str, cid: str, csecret: str):
        if not cid or not csecret:
            raise SystemExit("RUBRIK_CLIENT_ID and RUBRIK_CLIENT_SECRET must be set.")
        self.fqdn = fqdn
        self.cid = cid
        self.csecret = csecret
        self.tok = self._auth()

    def _auth(self) -> str:
        url = f"https://{self.fqdn}/api/client_token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.cid,
            "client_secret": self.csecret,
        }
        try:
            print(f"[AUTH] Connecting to {self.fqdn} ...")
            resp = requests.post(
                url,
                data=payload,
                proxies=PROXIES,
                timeout=REQUEST_TIMEOUT,
                verify=False,
            )
            resp.raise_for_status()
            print(f"[OK] Authenticated successfully to {self.fqdn}\n")
            return resp.json().get("access_token")
        except Exception as exc:
            print(f"[ERROR] Auth failed: {exc}")
            raise SystemExit(1)

    def q(self, query: str, vars: Optional[Dict] = None) -> Optional[Dict]:
        """Execute GraphQL query with shared timeout."""
        hdr = {"Authorization": f"Bearer {self.tok}", "Content-Type": "application/json"}
        try:
            resp = requests.post(
                f"https://{self.fqdn}/api/graphql",
                json={"query": query, "variables": vars or {}},
                headers=hdr,
                proxies=PROXIES,
                timeout=REQUEST_TIMEOUT,
                verify=False,
            )
            if resp.status_code != 200:
                print(f"[WARN] GraphQL {resp.status_code} {resp.reason}")
                try:
                    print(resp.text[:400])
                except Exception:
                    pass
                return None
            return resp.json()
        except requests.exceptions.Timeout:
            print("[TIMEOUT] Rubrik query timed out.")
            return None
        except Exception as exc:
            print(f"[ERROR] GraphQL query failed: {exc}")
            return None


# ==========================================
# Helper Functions
# ==========================================
def load_server_list(path: str, label: str) -> List[str]:
    if not path:
        raise SystemExit(f"[ERROR] {label} path not provided. Set SERVER_LIST_PATH or serverlist.")
    if not os.path.exists(path):
        raise SystemExit(f"[ERROR] {label} not found: {path}")
    with open(path) as handle:
        entries = [line.strip().lower() for line in handle if line.strip()]
    print(f"[INFO] Loaded {len(entries)} servers from {path} ({label})")
    return entries


def ensure_parent(path: str) -> None:
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)


def _safe_path_string(physical_path_field):
    if not physical_path_field:
        return "n/a"
    try:
        if isinstance(physical_path_field, list):
            return ", ".join([p.get("name", "") for p in physical_path_field]).lower()
        return physical_path_field.get("name", "n/a").lower()
    except Exception:
        return "n/a"


def fuzzy_match(server: str, fileset: Dict) -> bool:
    s = server.lower()
    return (s in fileset.get("server", "")) or (s in (fileset.get("path") or ""))


def latest_snapshot_after_cutoff(rsc: Rubrik, snappable_id: str) -> Tuple[str, str, int, str]:
    try:
        vars_json = json.loads(
            gpls.odsSnapshotListfromSnappableVars.replace("REPLACEME", snappable_id)
        )
    except Exception:
        vars_json = {"snappableId": snappable_id}
    vars_json.setdefault("first", 50)
    snaps = rsc.q(gpls.odsSnapshotListfromSnappable, vars_json)
    conn = snaps.get("data", {}).get("snapshotsListConnection") if snaps else None
    edges = (conn or {}).get("edges", []) if conn else []
    if not edges:
        return "NO", "N/A", 0, "N/A"

    latest = edges[0].get("node", {})
    sla_name = (latest.get("slaDomain") or {}).get("name", "N/A")
    dt = latest.get("date")
    try:
        snap_dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except Exception:
        snap_dt = None

    if not snap_dt:
        return "NO", "N/A", len(edges), sla_name

    now = datetime.now(timezone.utc)
    days_diff = (now.date() - snap_dt.date()).days
    status = "YES" if days_diff in (0, 1) else "NO"
    return status, snap_dt.strftime("%Y-%m-%d %H:%M:%S UTC"), len(edges), sla_name


# ==========================================
# Fileset Helpers
# ==========================================
def fetch_all_filesets(rsc: Rubrik) -> List[Dict]:
    print("[STEP] Fetching all filesets from Rubrik CDM...")
    all_fs: List[Dict] = []

    win_vars = json.loads(gpls.filesetWindowsVars)
    win_vars["first"] = 500
    win_data = rsc.q(gpls.filesetTemplateQuery, win_vars)
    win_edges = (
        win_data.get("data", {}).get("filesetTemplates", {}).get("edges", []) if win_data else []
    )
    for edge in win_edges:
        node = edge.get("node", {})
        fs_name = node.get("name", "N/A")
        cluster = node.get("cluster", {}).get("name", "N/A")
        children = node.get("physicalChildConnection", {}).get("edges", []) or []
        for child_edge in children:
            child = child_edge.get("node", {})
            all_fs.append(
                {
                    "snappable_id": child.get("id"),
                    "server": (child.get("name") or "n/a").lower(),
                    "fileset": fs_name,
                    "cluster": cluster,
                    "sla": (child.get("effectiveSlaDomain", {}) or {}).get("name", "N/A"),
                    "path": _safe_path_string(child.get("physicalPath")),
                    "type": "WINDOWS_FILESET",
                }
            )
    print(f"[OK] Found {len([x for x in all_fs if x['type'] == 'WINDOWS_FILESET'])} Windows filesets.")

    lin_vars = json.loads(gpls.filesetLinuxVars)
    lin_vars["first"] = 500
    lin_data = rsc.q(gpls.filesetTemplateQuery, lin_vars)
    lin_edges = (
        lin_data.get("data", {}).get("filesetTemplates", {}).get("edges", []) if lin_data else []
    )
    for edge in lin_edges:
        node = edge.get("node", {})
        fs_name = node.get("name", "N/A")
        cluster = node.get("cluster", {}).get("name", "N/A")
        children = node.get("physicalChildConnection", {}).get("edges", []) or []
        for child_edge in children:
            child = child_edge.get("node", {})
            all_fs.append(
                {
                    "snappable_id": child.get("id"),
                    "server": (child.get("name") or "n/a").lower(),
                    "fileset": fs_name,
                    "cluster": cluster,
                    "sla": (child.get("effectiveSlaDomain", {}) or {}).get("name", "N/A"),
                    "path": _safe_path_string(child.get("physicalPath")),
                    "type": "LINUX_FILESET",
                }
            )
    print(f"[OK] Found {len([x for x in all_fs if x['type'] == 'LINUX_FILESET'])} Linux filesets.")
    print(f"[INFO] Total filesets fetched: {len(all_fs)}")
    return all_fs


def check_filesets(rsc: Rubrik, serverlist: List[str]) -> List[Dict]:
    all_filesets = fetch_all_filesets(rsc)
    ensure_parent(ALL_FILESETS_DUMP)
    with open(ALL_FILESETS_DUMP, "w", encoding="utf-8") as handle:
        json.dump(all_filesets, handle, indent=2)
    print(f"[SAVE] Full fileset dump saved to {ALL_FILESETS_DUMP}\n")

    matches: List[Dict] = []
    for srv in serverlist:
        srv_matches = [fs for fs in all_filesets if fuzzy_match(srv, fs)]
        for match in srv_matches:
            match["_requested_server"] = srv
        matches.extend(srv_matches)
        if not srv_matches:
            print(f"[WARN] No fileset match for {srv}")

    print(f"[STEP] Checking last fileset backup for {len(matches)} matched entries...\n")

    results: List[Dict] = []
    for fs in matches:
        snappable_id = fs.get("snappable_id")
        if not snappable_id:
            results.append(
                {
                    "server": fs.get("_requested_server", fs.get("server", "n/a")),
                    "type": fs.get("type", "FILESET"),
                    "cluster": fs.get("cluster", "N/A"),
                    "in_rubrik": "NO",
                    "fileset": fs.get("fileset", "N/A"),
                    "last_backup": "N/A",
                    "status": "NO",
                    "snapshot_count": 0,
                    "sla_domain": fs.get("sla", "N/A"),
                }
            )
            continue

        status, dt_str, snap_count, sla_name = latest_snapshot_after_cutoff(rsc, snappable_id)
        server_display = fs.get("_requested_server", fs.get("server", "n/a"))
        results.append(
            {
                "server": server_display,
                "type": fs.get("type", "FILESET"),
                "cluster": fs.get("cluster", "N/A"),
                "in_rubrik": "YES",
                "fileset": fs.get("fileset", "N/A"),
                "last_backup": dt_str,
                "status": status,
                "snapshot_count": snap_count,
                "sla_domain": fs.get("sla", sla_name),
            }
        )
        print(
            f"{server_display:25} | Fileset | Snaps: {snap_count:3} | SLA: {fs.get('sla', sla_name):20} | Backup: {status:3} | {dt_str}"
        )
    return results


# ==========================================
# VM Snapshot Helpers
# ==========================================
def build_vm_object_index(rsc: Rubrik) -> Dict[str, str]:
    print("[STEP] Building Rubrik VM object index...")
    sla_vars = json.loads(gpls.slaListQueryVars)
    sla_data = rsc.q(gpls.slaListQuery, sla_vars)
    sla_edges = sla_data.get("data", {}).get("slaDomains", {}).get("edges", []) if sla_data else []
    idmap: Dict[str, str] = {}

    for edge in sla_edges:
        sla_id = edge.get("node", {}).get("id")
        if not sla_id:
            continue
        pobj = rsc.q(
            gpls.protectedObjectListQuery,
            json.loads(gpls.protectedObjectListQueryVars.replace("REPLACEME", sla_id)),
        )
        edges = (
            pobj.get("data", {}).get("slaProtectedObjects", {}).get("edges", []) if pobj else []
        )
        for obj_edge in edges:
            node = obj_edge.get("node", {})
            name = node.get("name")
            rid = node.get("id")
            if not name or not rid:
                continue
            idmap[name.lower()] = rid

    print(f"[OK] Indexed {len(idmap)} Rubrik objects.\n")
    return idmap


def check_vm_snapshots(rsc: Rubrik, serverlist: List[str], idmap: Dict[str, str]) -> List[Dict]:
    results: List[Dict] = []
    now = datetime.now(timezone.utc)

    for idx, srv in enumerate(serverlist, 1):
        if idx % 50 == 0:
            print(f"[HEARTBEAT] Processed {idx} servers for VM snapshots...")

        rid = idmap.get(srv)
        if not rid:
            results.append(
                {
                    "server": srv,
                    "in_rubrik": "NO",
                    "last_backup": "N/A",
                    "status": "NO",
                    "snapshot_count": 0,
                    "sla_domain": "N/A",
                }
            )
            continue

        try:
            vars_json = json.loads(
                gpls.odsSnapshotListfromSnappableVars.replace("REPLACEME", rid)
            )
        except Exception:
            vars_json = {"snappableId": rid}
        vars_json.setdefault("first", 50)

        snaps = rsc.q(gpls.odsSnapshotListfromSnappable, vars_json)
        conn = snaps.get("data", {}).get("snapshotsListConnection") if snaps else None
        edges = conn.get("edges", []) if conn else []
        if not edges:
            results.append(
                {
                    "server": srv,
                    "in_rubrik": "YES",
                    "last_backup": "N/A",
                    "status": "NO",
                    "snapshot_count": 0,
                    "sla_domain": "N/A",
                }
            )
            continue

        latest = edges[0].get("node", {})
        sla_name = (latest.get("slaDomain") or {}).get("name", "N/A")
        dt = latest.get("date")
        try:
            snap_dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            snap_dt = None

        if snap_dt:
            days_diff = (now.date() - snap_dt.date()).days
            backed_up = "YES" if days_diff in (0, 1) else "NO"
            dt_str = snap_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            backed_up = "NO"
            dt_str = "N/A"

        snapshot_count = len(edges)
        results.append(
            {
                "server": srv,
                "in_rubrik": "YES",
                "last_backup": dt_str,
                "status": backed_up,
                "snapshot_count": snapshot_count,
                "sla_domain": sla_name,
            }
        )
        print(
            f"{srv:25} | VM      | Snaps: {snapshot_count:3} | SLA: {sla_name:20} | Backup: {backed_up:3} | {dt_str}"
        )
    return results


# ==========================================
# SUMMARY
# ==========================================
def summarize(results: List[Dict], label: str) -> None:
    total = len(results)
    success = sum(1 for entry in results if entry.get("status") == "YES")
    failed = total - success
    print("=" * 55)
    print(f"{label} Summary")
    print(f"Total Servers : {total}")
    print(f"Successful    : {success}")
    print(f"Failed        : {failed}")
    print("=" * 55 + "\n")


def save_results(path: str, data: List[Dict], label: str) -> None:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    print(f"[SAVE] {label} results written to {path}")


# ==========================================
# MAIN
# ==========================================
def main():
    shared_path = SERVER_LIST_PATH or "L2Backup/serverslist5"
    serverlist = load_server_list(shared_path, "shared server list")

    fileset_serverlist = serverlist
    if FILESET_SERVER_LIST_PATH and FILESET_SERVER_LIST_PATH != shared_path:
        fileset_serverlist = load_server_list(FILESET_SERVER_LIST_PATH, "fileset server list")

    snapshot_serverlist = serverlist
    override = VMSNAPSHOT_SERVER_LIST_PATH
    if override and override != shared_path:
        snapshot_serverlist = load_server_list(override, "VM snapshot server list")

    rsc = Rubrik(RSC_FQDN, CID, CSECRET)

    fileset_results = check_filesets(rsc, fileset_serverlist)
    summarize(fileset_results, "Fileset")
    save_results(FILESET_OUT_FILE, fileset_results, "Fileset")

    vm_index = build_vm_object_index(rsc)
    vm_results = check_vm_snapshots(rsc, snapshot_serverlist, vm_index)
    summarize(vm_results, "VM Snapshot")
    save_results(SNAPSHOT_OUT_FILE, vm_results, "VM Snapshot")

    print("[DONE] Combined Rubrik backup checks complete.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[FATAL] {exc}")
        raise SystemExit(1)
