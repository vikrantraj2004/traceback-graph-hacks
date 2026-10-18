"""Pure rules that turn an assessment into SIMULATED containment proposals.

confirmed shipment   -> QUARANTINE_INVENTORY
potential shipment   -> PRECAUTIONARY_HOLD
unknown shipment     -> ESCALATE_FOR_REVIEW
provenance gap batch -> REQUEST_TRACEABILITY_RECORDS
Nothing here touches the database or the real world.
"""
from services.impact_assessment import CONFIRMED, POTENTIAL, UNKNOWN, RANK


def _evidence_text(shipment):
    return "\n".join(e["path_text"] for e in shipment["evidence"])


def propose_actions(assessment, incident_id):
    if not incident_id:
        raise ValueError("An incident is required to propose containment actions.")

    proposals = []
    for s in assessment["shipments"]:
        sid, loc = s["shipment_id"], f"{s['location_id']} ({s['location_name']})"
        batches = ", ".join(b["product_batch_id"] for b in s["product_batches"])
        if s["exposure"] == CONFIRMED:
            action_type = "QUARANTINE_INVENTORY"
            rationale = (f"Shipment {sid} has a fully verified path from the affected lot to {loc}. "
                         f"Quarantine the inventory from product batch(es) {batches} (simulated).")
        elif s["exposure"] == POTENTIAL:
            action_type = "PRECAUTIONARY_HOLD"
            rationale = (f"Shipment {sid} is linked to the affected lot only through an unverified "
                         f"record. Hold the goods from {batches} at {loc} until it is verified (simulated).")
        else:
            action_type = "ESCALATE_FOR_REVIEW"
            rationale = (f"Shipment {sid} carries {batches} whose provenance is incomplete. It cannot "
                         f"be cleared or linked to the incident; escalate for review (simulated).")
        proposals.append({
            "action_id": f"{incident_id}-{action_type}-{sid}",
            "action_type": action_type,
            "exposure": s["exposure"],
            "target_type": "Shipment",
            "target_id": sid,
            "rationale": rationale,
            "evidence": _evidence_text(s),
            "status": "PROPOSED",
        })

    for g in assessment["provenance_gaps"]:
        pr = g["production_batch_id"]
        proposals.append({
            "action_id": f"{incident_id}-REQUEST_TRACEABILITY_RECORDS-{pr}",
            "action_type": "REQUEST_TRACEABILITY_RECORDS",
            "exposure": UNKNOWN,
            "target_type": "ProductionBatch",
            "target_id": pr,
            "rationale": (f"Request component consumption records for {pr} so its exposure can be "
                          f"determined (simulated)."),
            "evidence": g["reason"],
            "status": "PROPOSED",
        })

    proposals.sort(key=lambda p: (-RANK[p["exposure"]], p["target_id"]))
    return proposals
