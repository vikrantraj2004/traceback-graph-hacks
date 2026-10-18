"""Pure tests (no database). Cover classification rules and test G (evidence integrity)."""
import re

from services.impact_assessment import CONFIRMED, POTENTIAL, UNKNOWN, assess


def row(lot, pr, pb, sh, loc, name, verified, qty, source="ERP batch record"):
    return {"lot_id": lot, "production_batch_id": pr, "product_batch_id": pb, "shipment_id": sh,
            "location_id": loc, "location_name": name, "verified": verified, "source": source,
            "quantity": qty}


def gap(pr, fac, pb, sh, loc, name, qty):
    return {"production_batch_id": pr, "facility_id": fac, "product_batch_id": pb,
            "shipment_id": sh, "location_id": loc, "location_name": name, "quantity": qty}


PATHS = [
    row("L-204", "PR-012", "PB-031", "SH-014", "WH-03", "North DC", True, 1000),
    row("L-204", "PR-013", "PB-032", "SH-015", "RT-11", "Retailer 11", True, 500),
    row("L-204", "PR-013", "PB-033", "SH-015", "RT-11", "Retailer 11", True, 300),
    row("L-204", "PR-013", "PB-033", "SH-016", "RT-12", "Retailer 12", True, 500),
    row("L-204", "PR-015", "PB-034", "SH-017", "WH-04", "East DC", False, 600, "handwritten line log"),
]
GAPS = [gap("PR-016", "FAC-A", "PB-050", "SH-019", "WH-04", "East DC", 400)]


def by_id(items, key):
    return {i[key]: i for i in items}


def test_summary_counts():
    s = assess(["L-204"], PATHS, GAPS)["summary"]
    assert s["confirmed_shipments"] == 3 and s["potential_shipments"] == 1 and s["unknown_shipments"] == 1
    assert s["confirmed_product_batches"] == 3 and s["potential_product_batches"] == 1
    assert s["unknown_product_batches"] == 1 and s["provenance_gaps"] == 1
    assert s["confirmed_locations"] == 3 and s["potential_locations"] == 1 and s["unknown_locations"] == 0


def test_shipment_and_batch_exposure():
    a = assess(["L-204"], PATHS, GAPS)
    ships = by_id(a["shipments"], "shipment_id")
    assert {k: v["exposure"] for k, v in ships.items()} == {
        "SH-014": CONFIRMED, "SH-015": CONFIRMED, "SH-016": CONFIRMED,
        "SH-017": POTENTIAL, "SH-019": UNKNOWN}
    batches = {b["product_batch_id"]: b["exposure"] for b in a["product_batches"]}
    assert batches == {"PB-031": CONFIRMED, "PB-032": CONFIRMED, "PB-033": CONFIRMED,
                       "PB-034": POTENTIAL, "PB-050": UNKNOWN}
    assert "PB-040" not in batches  # unaffected batch is never invented


def test_shared_destination_takes_strongest_exposure():
    locs = by_id(assess(["L-204"], PATHS, GAPS)["locations"], "location_id")
    assert locs["WH-04"]["exposure"] == POTENTIAL
    assert {s["shipment_id"] for s in locs["WH-04"]["shipments"]} == {"SH-017", "SH-019"}


def test_multiple_paths_same_shipment_are_merged():
    ship = by_id(assess(["L-204"], PATHS, GAPS)["shipments"], "shipment_id")["SH-015"]
    assert [b["product_batch_id"] for b in ship["product_batches"]] == ["PB-032", "PB-033"]
    assert len(ship["evidence"]) == 2


def test_missing_verified_flag_is_potential_not_confirmed():
    r = row("L-204", "PR-015", "PB-034", "SH-017", "WH-04", "East DC", None, 600)
    a = assess(["L-204"], [r], [])
    assert a["shipments"][0]["exposure"] == POTENTIAL


def test_precedence_confirmed_beats_potential():
    rows = [row("L-204", "PR-012", "PB-031", "SH-014", "WH-03", "North DC", False, 10),
            row("L-204", "PR-013", "PB-032", "SH-014", "WH-03", "North DC", True, 20)]
    a = assess(["L-204"], rows, [])
    assert a["shipments"][0]["exposure"] == CONFIRMED
    pbs = {b["product_batch_id"]: b["exposure"] for b in a["shipments"][0]["product_batches"]}
    assert pbs == {"PB-031": POTENTIAL, "PB-032": CONFIRMED}


def test_gap_without_shipment_is_still_reported_as_unknown():
    g = [gap("PR-016", "FAC-A", "PB-050", None, None, None, None)]
    a = assess(["L-204"], [], g)
    assert a["shipments"] == [] and len(a["provenance_gaps"]) == 1
    assert a["product_batches"] == [{"product_batch_id": "PB-050", "exposure": UNKNOWN}]


def test_empty_inputs_do_not_crash():
    a = assess(["L-204"], [], [])
    assert a["shipments"] == [] and a["provenance_gaps"] == []
    assert all(v == 0 for v in a["summary"].values())


def test_g_evidence_mentions_only_ids_from_query_results():
    allowed = set()
    for r in PATHS:
        allowed |= {r["lot_id"], r["production_batch_id"], r["product_batch_id"],
                    r["shipment_id"], r["location_id"]}
    for g in GAPS:
        allowed |= {g["production_batch_id"], g["facility_id"], g["product_batch_id"],
                    g["shipment_id"], g["location_id"]}
    a = assess(["L-204"], PATHS, GAPS)
    texts = [e["path_text"] for s in a["shipments"] for e in s["evidence"]]
    texts += [g["reason"] for g in a["provenance_gaps"]]
    mentioned = set()
    for t in texts:
        mentioned |= set(re.findall(r"\b[A-Z]{1,3}-[0-9A-Z]+\b", t))
    assert mentioned and mentioned <= allowed
