"""Database tests (need FalkorDB running). Cover tests A, B, C, D (gap), E."""
import pytest

from tools.investigation import (
    explain_batch, find_downstream_paths, identify_provenance_gaps,
    investigate, resolve_target, trace_affected_batches,
)


def pairs(result):
    return {(b["production_batch_id"], b["product_batch_id"], b["verified"]) for b in result["batches"]}


def test_seed_counts(graph):
    assert graph.ro_query("MATCH (n) RETURN count(n)").result_set[0][0] == 28
    assert graph.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0] == 28


def test_a_b_direct_and_multiple_paths(graph):
    res = trace_affected_batches(graph, "L-204")
    assert res["found"] is True
    assert pairs(res) == {
        ("PR-012", "PB-031", True), ("PR-013", "PB-032", True),
        ("PR-013", "PB-033", True), ("PR-015", "PB-034", False),
    }


def test_c_unaffected_batch_not_linked(graph):
    ids = {b["product_batch_id"] for b in trace_affected_batches(graph, "L-204")["batches"]}
    assert "PB-040" not in ids and "PB-050" not in ids
    assert pairs(trace_affected_batches(graph, "L-205")) == {("PR-014", "PB-040", True)}


def test_e_unknown_lot_is_controlled(graph):
    assert trace_affected_batches(graph, "L-999") == {"found": False, "lot_id": "L-999", "batches": []}


def test_invalid_id_rejected(graph):
    with pytest.raises(ValueError):
        trace_affected_batches(graph, "x; DROP")


def test_downstream_paths_l204(graph):
    paths = find_downstream_paths(graph, ["L-204"])
    got = {(p["shipment_id"], p["product_batch_id"], p["location_id"], p["verified"]) for p in paths}
    assert got == {
        ("SH-014", "PB-031", "WH-03", True), ("SH-015", "PB-032", "RT-11", True),
        ("SH-015", "PB-033", "RT-11", True), ("SH-016", "PB-033", "RT-12", True),
        ("SH-017", "PB-034", "WH-04", False),
    }
    assert len(paths) == 5
    assert not any(p["shipment_id"] in ("SH-018", "SH-019") for p in paths)


def test_d_provenance_gap_found(graph):
    gaps = identify_provenance_gaps(graph, ["L-204"])
    assert len(gaps) == 1
    g = gaps[0]
    assert (g["production_batch_id"], g["facility_id"], g["product_batch_id"],
            g["shipment_id"], g["location_id"], g["quantity"]) == ("PR-016", "FAC-A", "PB-050", "SH-019", "WH-04", 400)
    assert identify_provenance_gaps(graph, ["L-205"]) == []  # FAC-B has no gaps


def test_resolve_target(graph):
    r = resolve_target(graph, "L-204")
    assert r["found"] and r["incident"]["incident_id"] == "INC-001"
    assert r["supplier"]["supplier_id"] == "S-17" and r["lot_ids"] == ["L-204"]
    r = resolve_target(graph, "inc-001")  # case-insensitive input
    assert r["found"] and r["lot_ids"] == ["L-204"]
    assert resolve_target(graph, "L-205")["incident"] is None
    assert resolve_target(graph, "L-999")["found"] is False
    assert resolve_target(graph, "INC-999")["found"] is False


def test_investigate_l204_summary(graph):
    res = investigate(graph, "L-204")
    assert res["found"]
    assert res["assessment"]["summary"] == {
        "confirmed_shipments": 3, "potential_shipments": 1, "unknown_shipments": 1,
        "confirmed_product_batches": 3, "potential_product_batches": 1, "unknown_product_batches": 1,
        "confirmed_locations": 3, "potential_locations": 1, "unknown_locations": 0,
        "provenance_gaps": 1,
    }


def test_investigate_unknown_is_controlled(graph):
    res = investigate(graph, "L-999")
    assert res["found"] is False and "not found" in res["message"]


def test_explain_batch(graph):
    lots = ["L-204"]
    assert explain_batch(graph, "PB-031", lots)["verdict"] == "CONFIRMED"
    assert explain_batch(graph, "PB-033", lots)["verdict"] == "CONFIRMED"
    assert explain_batch(graph, "PB-034", lots)["verdict"] == "POTENTIAL"
    assert explain_batch(graph, "PB-040", lots)["verdict"] == "NOT_LINKED"
    assert explain_batch(graph, "PB-050", lots)["verdict"] == "UNKNOWN_PROVENANCE"
    assert explain_batch(graph, "PB-999", lots)["found"] is False
