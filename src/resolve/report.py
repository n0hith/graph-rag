"""reports/resolution_summary.md: the tracked record of a `resolve` run (the resolved data
itself is in data/resolved/, gitignored)."""

from __future__ import annotations

import datetime
from collections import Counter
from pathlib import Path

from src.eval.summary import _bullets, _git_head
from src.resolve.merge_entities import Resolution

KIND_TYPE = {"person": "Person", "company": "Company", "firm": "AuditFirm", "group": "RelatedPartyGroup"}


def write_resolution_summary(path: Path, res: Resolution) -> Path:
    ent = {e["id"]: e for e in res.entities}
    lines = ["# Entity resolution summary", "",
             f"Generated {datetime.date.today().isoformat()} from code at commit `{_git_head()}`. Resolved entities, "
             "relations, the merge log and the review list are in `data/resolved/` (gitignored).", "",
             "## Before and after merging", "",
             "Mentions: every place a fact names one (a director row, a KMP line, a subsidiary row, a related party, ...). "
             "Per-report names: distinct normalised names within one report. Entities: after merging across reports.", "",
             "| Kind | Mentions | Per-report names | Entities | In more than one report |", "|---|---|---|---|---|"]
    for kind, label in KIND_TYPE.items():
        ms = [m for m in res.mentions if m.kind == kind]
        per_report = len({(m.symbol, m.key) for m in ms})
        es = [e for e in res.entities if e["type"] == label]
        multi = sum(len(e["reports"]) > 1 for e in es)
        lines.append(f"| {label} | {len(ms)} | {per_report} | {len(es)} | {multi} |")
    lines.append("")

    lines += ["## Merge rules applied", ""]
    rules = Counter(r["rule"] if r["rule"].startswith(("override", "same name", "short name"))
                    else " ".join(r["rule"].split()[:2]) for r in res.log)
    simple = Counter()
    for rule, n in rules.items():
        simple[rule.split(":")[0] if rule.startswith(("override", "short name")) else rule] += n
    lines += _bullets([f"{rule}: {n}" for rule, n in simple.most_common()]) + [""]

    decisions = [r for r in res.log if r["rule"].startswith("override")]
    blocked = [r for r in res.log if r["rule"].startswith("never merged")]
    lines += ["## Hand-confirmed decisions (data/overrides/merges.csv)", ""]
    lines += _bullets([f"'{r['b']}' ({r['b_report']}) joined '{r['a']}' ({r['a_report']}) [{r['rule']}]"
                       if r["rule"].startswith("override merges.csv") else f"{r['rule']}: '{r['a']}' on '{r['b']}'"
                       for r in decisions]) or ["None."]
    lines += ["", "Recorded as relations, the companies staying separate: "
              + "; ".join(f"{r['type']} {ent[r['from']]['name']} -> {ent[r['to']]['name']}"
                          for r in res.relations if r["type"] in ("MERGED_INTO", "FORMERLY_NAMED")), "",
              "Rule: two rows of the same report's subsidiary list are always two companies. Merges it blocked in "
              f"this run: {len(blocked)}.", ""]
    lines += _bullets([f"{r['a']} ({r['a_report']} p.{r['a_page']}) / {r['b']} ({r['b_report']} p.{r['b_page']}), "
                       f"would have merged by: {r['would_have_been']}" for r in blocked]) + [""]

    for label, title in [("Person", "People in more than one report"), ("Company", "Companies in more than one report"),
                         ("AuditFirm", "Audit firms in more than one report")]:
        es = sorted((e for e in res.entities if e["type"] == label and len(e["reports"]) > 1),
                    key=lambda e: (-len(e["reports"]), e["name"]))
        lines += [f"## {title} ({len(es)})", ""]
        items = []
        for e in es:
            extra = f"DIN {', '.join(e['dins'])}; " if e.get("dins") else ""
            roles = f"; as {', '.join(r for r in e.get('roles', []) if r != 'reporter')}" if e.get("roles") else ""
            names = [a for a in e["aliases"] if a != e["name"]]
            items.append(f"**{e['name']}** ({extra}{', '.join(e['reports'])}{roles})"
                         + (f"; also printed as {', '.join(repr(n) for n in names)}" if names else ""))
        lines += (_bullets(items) or ["None."]) + [""]

    rel = Counter(r["type"] for r in res.relations)
    conflicts = [r for r in res.relations if r.get("status_conflict")]
    lines += ["## Relations", "", "| Relation | Count |", "|---|---|"]
    lines += [f"| {t} | {n} |" for t, n in rel.most_common()]
    lines += ["", "Status of a board seat or KMP role combines all its mentions: 'appointed' and 'current' both mean "
                  "current, only 'ceased' means the person left; every stated date is kept. A seat known only from "
                  "another company's report has no status.", "",
              f"Seats/roles whose mentions disagreed on status: {len(conflicts)}", ""]
    lines += _bullets([f"{ent[r['from']]['name']} -> {ent[r['to']]['name']} ({r['type']}): now {r['status']}"
                       for r in conflicts]) + [""]
    groups = [e for e in res.entities if e["type"] == "RelatedPartyGroup"]
    lines += ["Related-party groups (a category of parties, not one company; one node per report and label): "
              + "; ".join(f"{g['reported_by']}: {g['name']}" for g in groups), ""]

    lines += [f"## Uncertain matches for review ({len(res.uncertain)}), not merged", "",
              "Also in `data/resolved/uncertain.csv` (with a blank `decision` column). Confirmed merges or splits go in "
              "`data/overrides/merges.csv`: people by `to_din`; companies with `action` merge / split.", "",
              "| # | Kind | A | B | Why they might be the same |", "|---|---|---|---|---|"]
    for n, u in enumerate(res.uncertain, 1):
        a, b = ent.get(u.a_id, {}), ent.get(u.b_id, {})

        def label(e):
            if not e:
                return ""
            where = ", ".join(e.get("reports", []))
            extra = f"; DIN {', '.join(e['dins'])}" if e.get("dins") else ""
            country = f"; {', '.join(e['countries'])}" if e.get("countries") else ""
            return f"{e['name']} ({where}{extra}{country})"

        lines.append(f"| {n} | {u.kind} | {label(a)} | {label(b)} | {u.reason} |")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
