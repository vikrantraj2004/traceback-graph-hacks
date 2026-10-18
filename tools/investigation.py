"""Typed, read-only investigation tools. Every database read goes through graph.ro_query()."""
import json
import re
import sys

from graph import queries as q
from graph.connection import get_graph
from services.impact_assessment import CONFIRMED, POTENTIAL, UNKNOWN, assess

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
EXPECTED_REL_TYPES = ["USED_IN", "PRODUCED", "INCLUDED_IN", "DELIVERED_TO"]


def _check_id(value, name):
    if not isinstance(value, str) or not _ID_RE.match(value.strip()):
        raise ValueError(f"Invalid {name}: {value!r}")
    return value.strip().upper()


def _rows(graph, query, params):
    res = graph.ro_query(query, params=params)
    return res.result_set


def trace_affected_batches(graph, lot_id):
    """Query 1: lot -> production batch -> product batch (2 hops)."""
    lot_id = _check_id(lot_id, "lot_id")
    rows = _rows(graph, q.TRACE_AFFECTED_BATCHES, {"lot_id": lot_id})
    if not rows:
        return {"found": False, "lot_id": lot_id, "batches": []}
    batches = [
        {"production_batch_id": r[1], "product_batch_id": r[2], "verified": r[3], "source": r[4]}
        for r in rows if r[1] is not None
    ]
    return {"found": True, "lot_id": lot_id, "batches": batches}


def resolve_target(graph, identifier):
    """Resolve an incident id (INC-...) or a component lot id to lots (+ incident, supplier)."""
    ident = _check_id(identifier, "identifier")
    if ident.startswith("INC-"):
        rows = _rows(graph, q.GET_INCIDENT_LOTS, {"incident_id": ident})
        if not rows:
            return {"found": False, "input": ident,
                    "message": f"No incident {ident} with affected lots was found in the graph."}
        r0 = rows[0]
        return {
            "found": True, "input": ident,
            "incident": {"incident_id": r0[0], "severity": r0[1], "status": r0[2], "description": r0[3]},
            "lot_ids": sorted({r[4] for r in rows}),
            "supplier": None,
        }
    rows = _rows(graph, q.GET_LOT_CONTEXT, {"lot_id": ident})
    if not rows:
        return {"found": False, "input": ident,
                "message": f"Component lot {ident} was not found in the graph."}
    r0 = rows[0]
    incident = None
    for r in rows:
        if r[5] is not None:
            incident = {"incident_id": r[5], "severity": r[6], "status": r[7], "description": r[8]}
            break
    supplier = {"supplier_id": r0[3], "name": r0[4]} if r0[3] else None
    return {"found": True, "input": ident, "incident": incident, "lot_ids": [r0[0]],
            "supplier": supplier, "component_name": r0[1], "lot_status": r0[2]}


def find_downstream_paths(graph, lot_ids):
    """Queries 2+3: full lot -> destination paths, one row per path (the evidence)."""
    lot_ids = [_check_id(l, "lot_id") for l in lot_ids]
    keys = ["lot_id", "production_batch_id", "product_batch_id", "shipment_id", "location_id",
            "location_name", "verified", "source", "quantity", "rel_types"]
    paths = []
    for r in _rows(graph, q.DOWNSTREAM_PATHS, {"lot_ids": lot_ids}):
        row = dict(zip(keys, r))
        if row["rel_types"] != EXPECTED_REL_TYPES:  # evidence-integrity guard
            raise RuntimeError(f"Unexpected path shape from FalkorDB: {row['rel_types']}")
        paths.append(row)
    return paths


def identify_provenance_gaps(graph, lot_ids):
    """Query 4: production batches at affected facilities with no recorded components."""
    lot_ids = [_check_id(l, "lot_id") for l in lot_ids]
    keys = ["production_batch_id", "facility_id", "product_batch_id", "shipment_id",
            "location_id", "location_name", "quantity"]
    return [dict(zip(keys, r)) for r in _rows(graph, q.PROVENANCE_GAPS, {"lot_ids": lot_ids})]


def list_product_batches(graph):
    return [r[0] for r in _rows(graph, q.LIST_PRODUCT_BATCHES, {})]


def explain_batch(graph, product_batch_id, lot_ids):
    """Why is (or isn't) this product batch linked to the affected lot(s)?"""
    pb_id = _check_id(product_batch_id, "product_batch_id")
    lot_ids = [_check_id(l, "lot_id") for l in lot_ids]
    rows = _rows(graph, q.UPSTREAM_OF_BATCH, {"product_batch_id": pb_id})
    if not rows:
        return {"found": False, "product_batch_id": pb_id}
    producers, lots = {}, []
    for _, pr, fac, lot, verified, source in rows:
        if pr is not None:
            producers.setdefault(pr, {"production_batch_id": pr, "facility_id": fac, "lots": []})
        if lot is not None:
            producers[pr]["lots"].append(lot)
            lots.append({"lot_id": lot, "production_batch_id": pr, "verified": verified, "source": source})
    affected = [l for l in lots if l["lot_id"] in lot_ids]
    if any(l["verified"] is True for l in affected):
        verdict, text = CONFIRMED, "Linked to the affected lot through a verified record."
    elif affected:
        verdict, text = POTENTIAL, "Linked to the affected lot only through an unverified record."
    elif not producers or any(not p["lots"] for p in producers.values()):
        verdict, text = UNKNOWN, ("Provenance is incomplete: no recorded component consumption. "
                                  "It cannot be cleared.")
    else:
        verdict, text = "NOT_LINKED", ("No path from the affected lot(s) in the recorded provenance "
                                       "(it was built from other lots).")
    return {"found": True, "product_batch_id": pb_id, "verdict": verdict, "explanation": text,
            "producers": list(producers.values()), "upstream_lots": lots}


def investigate(graph, identifier):
    """Run the full read-only investigation and return structured findings."""
    target = resolve_target(graph, identifier)
    if not target["found"]:
        return {"found": False, "input": target["input"], "message": target["message"]}
    lot_ids = target["lot_ids"]
    paths = find_downstream_paths(graph, lot_ids)
    gaps = identify_provenance_gaps(graph, lot_ids)
    return {"found": True, "target": target, "paths": paths, "gap_rows": gaps,
            "assessment": assess(lot_ids, paths, gaps)}


if __name__ == "__main__":
    ident = sys.argv[1] if len(sys.argv) > 1 else "L-204"
    result = investigate(get_graph(), ident)
    if result["found"]:
        print(json.dumps(result["assessment"]["summary"], indent=2))
        for s in result["assessment"]["shipments"]:
            print(f"\n{s['shipment_id']} [{s['exposure']}] -> {s['location_id']}")
            for e in s["evidence"]:
                print("   ", e["path_text"])
    else:
        print(result["message"])
