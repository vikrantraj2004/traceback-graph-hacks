"""Pure exposure classification rules. No database access in this module.

Rules (documented, deterministic):
  CONFIRMED          every edge on the path from the affected lot is verified
  POTENTIAL          a path exists but the USED_IN edge is unverified (verified is not True)
  UNKNOWN_PROVENANCE production batch at an affected facility with no recorded components;
                     the graph can neither link it to the incident nor clear it
Precedence when one entity is reached several ways: CONFIRMED > POTENTIAL > UNKNOWN.
Absence of a path is never reported as "safe".
"""

CONFIRMED = "CONFIRMED"
POTENTIAL = "POTENTIAL"
UNKNOWN = "UNKNOWN_PROVENANCE"
RANK = {CONFIRMED: 3, POTENTIAL: 2, UNKNOWN: 1}


def _stronger(a, b):
    return a if RANK[a] >= RANK[b] else b


def _sort_key(item, id_key):
    return (-RANK[item["exposure"]], item[id_key])


def build_path(row):
    """Turn one DOWNSTREAM_PATHS row into an inspectable evidence path."""
    verified = row["verified"] is True
    source = row.get("source") or "no source recorded"
    tag = f"verified: {source}" if verified else f"UNVERIFIED: {source}"
    text = (
        f"{row['lot_id']} -[USED_IN, {tag}]-> {row['production_batch_id']} "
        f"-[PRODUCED]-> {row['product_batch_id']} "
        f"-[INCLUDED_IN, qty {row['quantity']}]-> {row['shipment_id']} "
        f"-[DELIVERED_TO]-> {row['location_id']}"
    )
    steps = [
        {"node": "ComponentLot", "id": row["lot_id"]},
        {"rel": "USED_IN", "verified": verified, "source": row.get("source")},
        {"node": "ProductionBatch", "id": row["production_batch_id"]},
        {"rel": "PRODUCED"},
        {"node": "ProductBatch", "id": row["product_batch_id"]},
        {"rel": "INCLUDED_IN", "quantity": row["quantity"]},
        {"node": "Shipment", "id": row["shipment_id"]},
        {"rel": "DELIVERED_TO"},
        {"node": "Location", "id": row["location_id"]},
    ]
    return {"exposure": CONFIRMED if verified else POTENTIAL, "path_text": text, "steps": steps}


def _gap_evidence(g):
    return {
        "exposure": UNKNOWN,
        "path_text": (
            f"{g['production_batch_id']} [facility {g['facility_id']}, no recorded component "
            f"consumption] -[PRODUCED]-> {g['product_batch_id']} "
            f"-[INCLUDED_IN, qty {g['quantity']}]-> {g['shipment_id']} "
            f"-[DELIVERED_TO]-> {g['location_id']}"
        ),
        "steps": [],
    }


def assess(lot_ids, path_rows, gap_rows):
    shipments = {}

    def add(sid, loc_id, loc_name, exposure, pb_id, qty, evidence):
        s = shipments.setdefault(
            sid,
            {"shipment_id": sid, "location_id": loc_id, "location_name": loc_name,
             "exposure": exposure, "product_batches": {}, "evidence": []},
        )
        s["exposure"] = _stronger(s["exposure"], exposure)
        pb = s["product_batches"].setdefault(pb_id, {"quantity": qty, "exposure": exposure})
        pb["exposure"] = _stronger(pb["exposure"], exposure)
        s["evidence"].append(evidence)

    for row in path_rows:
        ev = build_path(row)
        add(row["shipment_id"], row["location_id"], row["location_name"], ev["exposure"],
            row["product_batch_id"], row["quantity"], ev)

    gaps = {}
    gap_batches_without_shipment = {}
    for g in gap_rows:
        pr = g["production_batch_id"]
        gap = gaps.setdefault(pr, {
            "production_batch_id": pr,
            "facility_id": g["facility_id"],
            "product_batches": [],
            "reason": (
                f"{pr} was made at {g['facility_id']}, the same facility as production batch(es) "
                f"that consumed the affected lot(s), but has no recorded component consumption. "
                f"The graph can neither link it to the incident nor clear it."
            ),
        })
        pb = g["product_batch_id"]
        if pb and pb not in gap["product_batches"]:
            gap["product_batches"].append(pb)
        if g["shipment_id"]:
            add(g["shipment_id"], g["location_id"], g["location_name"], UNKNOWN, pb,
                g["quantity"], _gap_evidence(g))
        elif pb:
            gap_batches_without_shipment[pb] = UNKNOWN

    # Roll shipments up into product batches and locations.
    batches = dict(gap_batches_without_shipment)
    locations = {}
    for s in shipments.values():
        for pb_id, info in s["product_batches"].items():
            batches[pb_id] = _stronger(batches.get(pb_id, UNKNOWN), info["exposure"])
        loc = locations.setdefault(
            s["location_id"],
            {"location_id": s["location_id"], "name": s["location_name"],
             "exposure": s["exposure"], "shipments": []},
        )
        loc["exposure"] = _stronger(loc["exposure"], s["exposure"])
        loc["shipments"].append({"shipment_id": s["shipment_id"], "exposure": s["exposure"]})

    shipment_list = []
    for s in shipments.values():
        s = dict(s)
        s["product_batches"] = sorted(
            ({"product_batch_id": k, **v} for k, v in s["product_batches"].items()),
            key=lambda x: x["product_batch_id"])
        shipment_list.append(s)
    shipment_list.sort(key=lambda x: _sort_key(x, "shipment_id"))

    batch_list = sorted(({"product_batch_id": k, "exposure": v} for k, v in batches.items()),
                        key=lambda x: _sort_key(x, "product_batch_id"))
    location_list = sorted(locations.values(), key=lambda x: _sort_key(x, "location_id"))
    gap_list = sorted(gaps.values(), key=lambda x: x["production_batch_id"])

    def count(items, exposure):
        return sum(1 for i in items if i["exposure"] == exposure)

    summary = {
        "confirmed_shipments": count(shipment_list, CONFIRMED),
        "potential_shipments": count(shipment_list, POTENTIAL),
        "unknown_shipments": count(shipment_list, UNKNOWN),
        "confirmed_product_batches": count(batch_list, CONFIRMED),
        "potential_product_batches": count(batch_list, POTENTIAL),
        "unknown_product_batches": count(batch_list, UNKNOWN),
        "confirmed_locations": count(location_list, CONFIRMED),
        "potential_locations": count(location_list, POTENTIAL),
        "unknown_locations": count(location_list, UNKNOWN),
        "provenance_gaps": len(gap_list),
    }
    return {
        "lot_ids": list(lot_ids),
        "summary": summary,
        "shipments": shipment_list,
        "product_batches": batch_list,
        "locations": location_list,
        "provenance_gaps": gap_list,
    }
