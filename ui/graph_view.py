"""Graphviz (DOT) rendering of an investigation. Pure Python: no database, no Streamlit.

The graph is drawn ONLY from query results (result["paths"], result["gap_rows"],
result["assessment"], and optionally one explain_batch() result), so every node and edge
comes from FalkorDB. The only invented shapes are the grey "missing record" placeholders
that mark provenance gaps, and they carry no IDs.
"""
from services.impact_assessment import CONFIRMED, POTENTIAL, RANK, UNKNOWN

NOT_LINKED = "NOT_LINKED"
COLORS = {CONFIRMED: "#F2747A", POTENTIAL: "#F0A35A", UNKNOWN: "#E5C65C", NOT_LINKED: "#5FCB8B",
          "LOT": "#34D399", "NEUTRAL": "#6B8577"}
LEGEND = [("LOT", "Affected lot"), (CONFIRMED, "Confirmed"), (POTENTIAL, "Potential"),
          (UNKNOWN, "Unknown provenance"), (NOT_LINKED, "Not linked"),]


def _q(text):
    """Quote a DOT string."""
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _stronger(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return a if RANK.get(a, 0) >= RANK.get(b, 0) else b


class _Dot:
    def __init__(self):
        self.nodes, self.edges = {}, {}

    def node(self, nid, label, kind, sub=None):
        self.nodes.setdefault(nid, {"label": label, "kind": kind, "sub": sub})

    def edge(self, a, b, label, dashed=False, kind=None):
        self.edges.setdefault((a, b, label), {"dashed": dashed, "kind": kind})

    def render(self):
        lines = ["digraph TraceBack {",
                 '  rankdir=LR; bgcolor="transparent"; nodesep=0.25; ranksep=0.7; pad=0.2;',
                 '  node [shape=box, style="filled,rounded", fontname="Helvetica", fontsize=11, '
                 'fontcolor="#EEF6F1", margin="0.14,0.07"];',
                 '  edge [color="#3B5A4A", fontname="Helvetica", fontsize=8, fontcolor="#86A396", '
                 'arrowsize=0.7];']
        for nid, n in self.nodes.items():
            color = COLORS.get(n["kind"], COLORS["NEUTRAL"])
            label = n["label"] + (f"\n{n['sub']}" if n["sub"] else "")
            extra = ' style="filled,rounded,dashed" fontcolor="#9AB5A6"' if n["kind"] == "MISSING" else ""
            pen = 2 if n["kind"] == "LOT" else 1.4
            lines.append(f'  {_q(nid)} [label={_q(label)}, color="{color}", '
                         f'fillcolor="{color}26", penwidth={pen}{"," + extra if extra else ""}];')
        for (a, b, label), e in self.edges.items():
            attrs = [f"label={_q(label)}"]
            if e["dashed"]:
                attrs += ['style=dashed', 'color="#F0A35A"']
            lines.append(f"  {_q(a)} -> {_q(b)} [{', '.join(attrs)}];")
        lines.append("}")
        return "\n".join(lines)


def build_dot(result, compare=None):
    """DOT source for one investigate() result, plus an optional explain_batch() comparison."""
    d = _Dot()
    a = result["assessment"]
    ship = {s["shipment_id"]: s["exposure"] for s in a["shipments"]}
    batch = {b["product_batch_id"]: b["exposure"] for b in a["product_batches"]}
    loc = {x["location_id"]: x["exposure"] for x in a["locations"]}
    prod = {}

    for r in result["paths"]:
        prod[r["production_batch_id"]] = _stronger(
            prod.get(r["production_batch_id"]), CONFIRMED if r["verified"] is True else POTENTIAL)
    for g in result["gap_rows"]:
        prod.setdefault(g["production_batch_id"], UNKNOWN)

    def chain(pr, pb, sh, lc, lc_name, qty):
        d.node(pr, pr, prod.get(pr, UNKNOWN))
        if pb:
            d.node(pb, pb, batch.get(pb, UNKNOWN))
            d.edge(pr, pb, "PRODUCED")
        if pb and sh:
            d.node(sh, sh, ship.get(sh, UNKNOWN))
            d.edge(pb, sh, f"INCLUDED_IN qty {qty}")
        if sh and lc:
            d.node(lc, lc, loc.get(lc, UNKNOWN), sub=lc_name)
            d.edge(sh, lc, "DELIVERED_TO")

    for r in result["paths"]:
        d.node(r["lot_id"], r["lot_id"], "LOT", sub="affected lot")
        d.edge(r["lot_id"], r["production_batch_id"],
               "USED_IN" if r["verified"] is True else "USED_IN (unverified)",
               dashed=r["verified"] is not True)
        chain(r["production_batch_id"], r["product_batch_id"], r["shipment_id"],
              r["location_id"], r["location_name"], r["quantity"])

    for g in result["gap_rows"]:
        pr = g["production_batch_id"]
        d.node(f"missing:{pr}", "no component\nrecords", "MISSING")
        d.edge(f"missing:{pr}", pr, "USED_IN missing", dashed=True)
        chain(pr, g["product_batch_id"], g["shipment_id"], g["location_id"],
              g["location_name"], g["quantity"])

    if compare and compare.get("found"):
        pb_id = compare["product_batch_id"]
        verdict = compare["verdict"]
        if pb_id not in d.nodes:
            d.node(pb_id, pb_id, verdict)
        for p in compare["producers"]:
            d.node(p["production_batch_id"], p["production_batch_id"],
                   prod.get(p["production_batch_id"], NOT_LINKED if verdict == NOT_LINKED else verdict))
            d.edge(p["production_batch_id"], pb_id, "PRODUCED")
        for lot in compare["upstream_lots"]:
            d.node(lot["lot_id"], lot["lot_id"], "LOT" if lot["lot_id"] in result["target"]["lot_ids"]
                   else "NEUTRAL", sub=None if lot["lot_id"] in result["target"]["lot_ids"] else "other lot")
            d.edge(lot["lot_id"], lot["production_batch_id"],
                   "USED_IN" if lot["verified"] is True else "USED_IN (unverified)",
                   dashed=lot["verified"] is not True)
    return d.render()
