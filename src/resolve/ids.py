"""Stable ids for resolved entities: data/resolved/id_registry.csv (committed).

Companies are keyed by CIN and people by DIN when they have one. Everything else gets an id
generated once (C-000001, P-000001, F-000001, G-000001) and saved with the keys that
recognise the entity again: its normalised names (with country, for companies), its FRN
(audit firms), its report and label (related-party groups). A later run reuses the saved id
of the entity that shares a key; only an entity matching none gets a new id. An id is never
given to a different entity: if two saved ids now describe one entity (a new merge), the
older one is kept and the other is marked retired, pointing at it; if one saved id now
matches two entities (a new split), the closer match keeps it and the other gets a new id.
"""

from __future__ import annotations

import csv
import datetime
from dataclasses import dataclass, field
from pathlib import Path

from src.resolve.normalize import company_name, person_key

PREFIX = {"Company": "C", "Person": "P", "AuditFirm": "F", "RelatedPartyGroup": "G"}
FIELDS = ["uid", "type", "name", "keys", "status", "replaced_by", "first_seen"]
KEY_SEP = " | "


@dataclass
class RegistryRow:
    uid: str
    type: str
    name: str
    keys: set[str]
    status: str = "active"  # active | retired | unused (not in the latest run)
    replaced_by: str = ""
    first_seen: str = ""


@dataclass
class Registry:
    rows: dict[str, RegistryRow] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Registry":
        reg = cls()
        if path.exists():
            with path.open(encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    reg.rows[r["uid"]] = RegistryRow(r["uid"], r["type"], r["name"],
                                                     set(filter(None, r["keys"].split(KEY_SEP))), r["status"],
                                                     r["replaced_by"], r["first_seen"])
        return reg

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            for r in sorted(self.rows.values(), key=lambda r: (r.type, r.uid)):
                w.writerow({"uid": r.uid, "type": r.type, "name": r.name, "keys": KEY_SEP.join(sorted(r.keys)),
                            "status": r.status, "replaced_by": r.replaced_by, "first_seen": r.first_seen})

    def next_uid(self, etype: str) -> str:
        prefix = PREFIX[etype] + "-"
        used = [int(u[len(prefix):]) for u in self.rows if u.startswith(prefix) and u[len(prefix):].isdigit()]
        return f"{prefix}{max(used, default=0) + 1:06d}"


def entity_keys(e: dict) -> set[str]:
    """What recognises an entity without a CIN/DIN across runs."""
    if e["type"] == "Company":
        countries = e.get("countries") or [""]
        return {f"{company_name(a).key}@{c.lower()}" for a in e["aliases"] for c in countries}
    if e["type"] == "Person":
        return {f"{person_key(a)}@{r}" for a in e["aliases"] for r in e["reports"]}
    if e["type"] == "AuditFirm":
        keys = {f"name:{company_name(a).key}" for a in e["aliases"]}
        if e.get("firm_registration_no"):
            keys.add(f"frn:{e['firm_registration_no']}")
        return keys
    return {f"{e['reported_by']}:{company_name(e['name']).key}"}


def _generated(row: RegistryRow) -> bool:
    return row.uid.startswith(PREFIX[row.type] + "-")


def natural_uid(e: dict) -> str | None:
    if e["type"] == "Company" and e.get("cin"):
        return e["cin"]
    if e["type"] == "Person" and e.get("din"):
        return e["din"]
    return None


def assign_uids(entities: list[dict], registry: Registry, today: str | None = None) -> tuple[dict[str, str], list[str]]:
    """Map each entity's run-local id to its stable uid, updating `registry`. Returns
    (run id -> uid, notes on retired/new ids)."""
    today = today or datetime.date.today().isoformat()
    out: dict[str, str] = {}
    notes: list[str] = []
    claimed: set[str] = set()
    pending = []
    for e in entities:
        keys = entity_keys(e)
        uid = natural_uid(e)
        if uid:
            row = registry.rows.get(uid)
            if row is None:
                registry.rows[uid] = RegistryRow(uid, e["type"], e["name"], keys, first_seen=today)
            out[e["id"]] = uid
            # A generated id this entity had before its CIN/DIN was known: retired, pointing here.
            for old in registry.rows.values():
                if _generated(old) and old.type == e["type"] and old.status != "retired" and old.keys & keys:
                    old.status, old.replaced_by = "retired", uid
                    notes.append(f"{old.uid} retired: now keyed by {uid}")
            continue
        candidates = sorted(((len(row.keys & keys), row.uid) for row in registry.rows.values()
                             if _generated(row) and row.type == e["type"] and row.status != "retired"
                             and row.keys & keys), key=lambda x: (-x[0], x[1]))
        pending.append((e, keys, candidates))
    # Generated ids: the best-overlapping entity claims a saved id first.
    pending.sort(key=lambda p: -(p[2][0][0] if p[2] else 0))
    for e, keys, candidates in pending:
        uid = next((u for _, u in candidates if u not in claimed), None)
        if uid is None:
            uid = registry.next_uid(e["type"])
            registry.rows[uid] = RegistryRow(uid, e["type"], e["name"], set(), first_seen=today)
            if candidates:
                notes.append(f"{uid} new for '{e['name']}': its saved id {candidates[0][1]} went to a closer match")
        claimed.add(uid)
        out[e["id"]] = uid
    # Saved ids nobody claimed that now describe part of a claimed entity: two saved entities
    # became one. The kept id is the claimed one; the others are retired, pointing at it.
    for e, keys, candidates in pending:
        for _, other in candidates:
            if other not in claimed and registry.rows[other].status != "retired":
                registry.rows[other].status, registry.rows[other].replaced_by = "retired", out[e["id"]]
                notes.append(f"{other} retired: merged into {out[e['id']]} ('{e['name']}')")
    in_use = set(out.values())
    for uid, row in registry.rows.items():
        if uid in in_use:
            row.status = "active"
            ent = next(e for e in entities if out[e["id"]] == uid)
            row.name = ent["name"]
            row.keys |= entity_keys(ent)
        elif row.status == "active":
            row.status = "unused"
    return out, notes
