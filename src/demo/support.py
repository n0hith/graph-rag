"""What the demo page shows beyond the answer: the graph paths, the answer nodes, and the sources
that support the answer (not every page the query or the retriever touched).

- Graph route: the answer nodes are the returned nodes the answer names (other than the entities
  the question names). The supporting paths are the ones that reach an answer node (all paths, if
  the answer names none, e.g. a count). A fact's sources are its company's own report where that
  report states it; pages where another report repeats it (e.g. a director's other directorships)
  are left out.
- Baseline: the pages the answer cites ("[Tata Steel Limited, pp. 426, 299]"), each checked
  against the retrieved excerpts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from neo4j.graph import Node, Path, Relationship

from src.eval.score import name_in, norm_tokens
from src.qa.answer import _walk
from src.qa.company_filter import companies_named

MAX_GRAPH_PATHS = 150
EDGE_FACTS = ("role", "title", "category", "status", "stake_pct", "nature", "amount_inr_crore", "appointed_on",
              "ceased_on")


@dataclass
class GNode:
    id: str
    name: str
    label: str
    uid: str | None = None
    symbol: str | None = None  # NSE symbol, for the pilot companies
    aliases: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class GEdge:
    id: str
    start: str
    end: str
    type: str
    evidence: list[tuple[str, str, int]] = field(default_factory=list)  # (reported_by, doc, page)
    facts: dict = field(default_factory=dict)


@dataclass
class GraphData:
    nodes: dict[str, GNode] = field(default_factory=dict)
    edges: dict[str, GEdge] = field(default_factory=dict)
    paths: list[tuple[list[str], list[str]]] = field(default_factory=list)  # (node ids, edge ids)
    truncated: int = 0  # paths left out of the view


def _gnode(n: Node) -> GNode:
    detail = n.get("din") and f"DIN {n.get('din')}" or n.get("cin") and f"CIN {n.get('cin')}" or ""
    return GNode(n.element_id, n.get("name") or n.get("uid") or "?", next(iter(n.labels), ""), n.get("uid"),
                 n.get("nse_symbol"), list(n.get("aliases") or []), detail)


def _gedge(r: Relationship) -> GEdge:
    evidence = list(zip(r.get("reported_by") or [None] * len(r.get("source_doc") or []),
                        r.get("source_doc") or [], r.get("page") or []))
    facts = {k: r.get(k) for k in EDGE_FACTS if r.get(k) not in (None, "", [])}
    return GEdge(r.element_id, r.start_node.element_id, r.end_node.element_id, r.type, evidence, facts)


def graph_data(records, max_paths: int = MAX_GRAPH_PATHS) -> GraphData:
    """The paths (and bare relationships) in the query's records, as plain data."""
    paths: list[Path] = []
    rels: list[Relationship] = []
    for record in records:
        for value in record.values():
            _walk(value, paths, rels)
    data = GraphData()
    on_paths = {r.element_id for p in paths for r in p.relationships}
    units = [(list(p.nodes), list(p.relationships)) for p in paths]
    units += [([r.start_node, r.end_node], [r]) for r in rels if r.element_id not in on_paths]
    seen = set()
    for nodes, rs in units:
        key = tuple(r.element_id for r in rs) or tuple(n.element_id for n in nodes)
        if key in seen:
            continue
        seen.add(key)
        if len(data.paths) == max_paths:
            data.truncated += 1
            continue
        for n in nodes:
            data.nodes.setdefault(n.element_id, _gnode(n))
        for r in rs:
            data.edges.setdefault(r.element_id, _gedge(r))
        data.paths.append(([n.element_id for n in nodes], [r.element_id for r in rs]))
    return data


def answer_nodes(data: GraphData, answer: str, entity_uids: set[str]) -> set[str]:
    """Nodes the answer names, other than the entities named in the question."""
    text = norm_tokens(answer)
    return {n.id for n in data.nodes.values()
            if n.uid not in entity_uids and any(name_in(norm_tokens(v), text) for v in [n.name, *n.aliases] if v)}


def supporting_sources(data: GraphData, answer_ids: set[str]) -> list[str]:
    """'DOC.pdf p.N' for the facts on the paths that reach an answer node, own-report pages only
    where the company's own report states the fact."""
    paths = [p for p in data.paths if answer_ids & set(p[0])] if answer_ids else data.paths
    out = []
    for _, edge_ids in paths:
        for eid in edge_ids:
            e = data.edges[eid]
            own = {data.nodes[e.start].symbol, data.nodes[e.end].symbol} - {None}
            kept = [ev for ev in e.evidence if ev[0] in own] or e.evidence
            out += [f"{doc} p.{page}" for _, doc, page in kept]
    return list(dict.fromkeys(out))


# ---------------------------------------------------------------- baseline citations

_CITATION = re.compile(r"\[([^\[\]]+)\]")
_PART = re.compile(r"^\s*(.+?),\s*pp?\.\s*(.+?)\s*$")
_RETRIEVED = re.compile(r"(\S+\.pdf) pp?\.(\d+)(?:-(\d+))?")


def _pages(text: str) -> list[int]:
    pages = []
    for a, b in re.findall(r"(\d+)(?:\s*[-–]\s*(\d+))?", text):
        start, end = int(a), int(b or a)
        pages += list(range(start, min(end, start + 20) + 1)) if end >= start else [start]
    return pages


def cited_sources(answer: str, retrieved: list[str]) -> list[str]:
    """The pages the baseline's answer cites, as 'DOC.pdf p.N'; a page outside every retrieved
    excerpt is marked."""
    covered = set()
    for s in retrieved:
        m = _RETRIEVED.match(s)
        if m:
            covered |= {(m.group(1), p) for p in range(int(m.group(2)), int(m.group(3) or m.group(2)) + 1)}
    out = []
    for citation in _CITATION.findall(answer):
        for part in citation.split(";"):
            m = _PART.match(part)
            symbols = companies_named(m.group(1)) if m else []
            if not symbols:
                continue
            doc = f"{symbols[0]}.pdf"
            out += [f"{doc} p.{p}" + ("" if (doc, p) in covered else " (not in the retrieved excerpts)")
                    for p in _pages(m.group(2))]
    return list(dict.fromkeys(out))


# ---------------------------------------------------------------- view

COLOURS = {"answer": "#f2b134", "question": "#4c8bf5", "other": "#8b93a7"}
CANVAS = "#161a23"  # a shade above Streamlit's dark background, so the view reads as a panel
LABEL, EDGE, EDGE_LABEL = "#e6e8ee", "#5c6578", "#8b93a7"

_VIEW_OPTIONS = {
    "nodes": {"shape": "dot", "size": 9, "borderWidth": 1,
              "font": {"size": 12, "color": LABEL, "strokeWidth": 3, "strokeColor": CANVAS}},
    "edges": {"color": {"color": EDGE, "highlight": "#c4c9d4", "hover": "#c4c9d4"}, "width": 1,
              "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}}, "smooth": {"type": "continuous"},
              "font": {"size": 8, "color": EDGE_LABEL, "strokeWidth": 0, "align": "top"}},
    # Long springs and overlap avoidance keep the labels apart; the layout settles, then freezes.
    "layout": {"randomSeed": 3},
    "physics": {"solver": "forceAtlas2Based",
                "forceAtlas2Based": {"gravitationalConstant": -80, "springLength": 180, "avoidOverlap": 1},
                "stabilization": {"iterations": 300, "fit": True}},
    "interaction": {"hover": True, "navigationButtons": False, "keyboard": False, "tooltipDelay": 150},
}

# Fill the iframe with no margins (no inner scrollbar), dark tooltips, and the empty heading pyvis adds dropped.
_VIEW_CSS = f"""<style>
html, body {{ margin: 0; padding: 0; height: 100%; overflow: hidden; background: {CANVAS}; }}
.card, .card-body {{ border: 0 !important; padding: 0 !important; margin: 0 !important; }}
#mynetwork {{ width: 100% !important; height: 100vh !important; border: 0 !important; float: none !important; }}
div.vis-tooltip {{ background: #262b37; color: {LABEL}; border: 1px solid #3a4152; border-radius: 4px;
  font: 12px/1.4 sans-serif; white-space: pre-line; }}
</style>"""

# Once the layout settles: stop the physics (nodes stay where they landed) and zoom to fit them, with a
# margin for the labels (fit only counts the nodes). The layout can finish before this runs, so it
# also checks after a short wait.
_FIT_JS = """<script>
function fitView() { network.fit({animation: false}); network.moveTo({scale: network.getScale() * 0.88}); }
function settle() { network.setOptions({physics: false}); fitView(); }
network.once("stabilizationIterationsDone", settle);
network.once("stabilized", settle);
setTimeout(settle, 2500);
window.addEventListener("resize", fitView);
</script>"""


def _safe(text) -> str:
    """Database text goes into an inlined script: no angle brackets, so it can't close the tag."""
    return str(text).replace("<", "‹").replace(">", "›")


def render_html(data: GraphData, answer_ids: set[str], question_ids: set[str]) -> str:
    """An interactive view (pyvis / vis-network, inlined so it works offline), sized to fill its iframe."""
    from pyvis.network import Network

    net = Network(height="100vh", width="100%", directed=True, cdn_resources="in_line", bgcolor=CANVAS,
                  font_color=LABEL)
    for n in data.nodes.values():
        kind = "answer" if n.id in answer_ids else "question" if n.id in question_ids else "other"
        title = "\n".join(x for x in (f"{n.label}: {n.name}", n.detail) if x)
        colour = COLOURS[kind]
        net.add_node(n.id, label=_safe(n.name), title=_safe(title), size=9,
                     color={"background": colour, "border": "#ffffff" if kind == "answer" else colour,
                            "highlight": {"background": colour, "border": "#ffffff"},
                            "hover": {"background": colour, "border": "#ffffff"}},
                     borderWidth=2 if kind == "answer" else 1)
    for e in data.edges.values():
        lines = [e.type, *(f"{k}: {v}" for k, v in e.facts.items()),
                 "sources: " + ", ".join(f"{doc} p.{page}" for _, doc, page in e.evidence)]
        net.add_edge(e.start, e.end, label=_safe(e.type), title=_safe("\n".join(lines)))
    net.set_options(json.dumps(_VIEW_OPTIONS))
    html = net.generate_html(notebook=False)
    # pyvis's template also pulls Bootstrap from a CDN for menus this view doesn't use.
    html = re.sub(r"<(link|script)\s[^>]*bootstrap[^>]*>(\s*</script>)?", "", html)
    html = re.sub(r"<center>\s*<h1>\s*</h1>\s*</center>", "", html)
    return html.replace("</head>", _VIEW_CSS + "</head>", 1).replace("</body>", _FIT_JS + "</body>", 1)
