"""Action persistence and the human-approval gate. All actions are SIMULATED."""
from datetime import datetime, timezone

from graph import queries as q

VALID_DECISIONS = ("APPROVED", "REJECTED")
_EXPOSURE_ORDER = {"CONFIRMED": 0, "POTENTIAL": 1, "UNKNOWN_PROVENANCE": 2}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def persist_proposals(graph, incident_id, proposals):
    """Write proposals as ContainmentAction nodes with status PROPOSED (idempotent)."""
    count = graph.ro_query(q.CHECK_INCIDENT, params={"incident_id": incident_id}).result_set[0][0]
    if count == 0:
        raise ValueError(f"Incident {incident_id!r} not found; cannot record actions.")
    for p in proposals:  # validate everything before writing anything
        if p["target_type"] not in q.TARGET_ID_PROPS:
            raise ValueError(f"Unsupported target type: {p['target_type']!r}")
        exists = graph.ro_query(q.target_exists_query(p["target_type"]),
                                params={"target_id": p["target_id"]}).result_set[0][0]
        if exists == 0:
            raise ValueError(f"Target {p['target_type']} {p['target_id']!r} not found in the graph.")
    now = _now()
    for p in proposals:
        graph.query(q.UPSERT_PROPOSED_ACTION, params={
            "incident_id": incident_id, "action_id": p["action_id"], "action_type": p["action_type"],
            "exposure": p["exposure"], "target_type": p["target_type"], "target_id": p["target_id"],
            "rationale": p["rationale"], "evidence": p["evidence"], "now": now})
        graph.query(q.link_target_query(p["target_type"]),
                    params={"action_id": p["action_id"], "target_id": p["target_id"]})
    return len(proposals)


def record_action_decision(graph, action_id, decision, reviewer, note=""):
    """The approval gate: an explicit decision and a named reviewer are both required."""
    decision = (decision or "").strip().upper()
    if decision not in VALID_DECISIONS:
        raise ValueError(f"Decision must be one of {VALID_DECISIONS}, got {decision!r}.")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("A named human reviewer is required to approve or reject an action.")
    rows = graph.ro_query(q.GET_ACTION_STATUS, params={"action_id": action_id}).result_set
    if not rows:
        raise LookupError(f"Action {action_id!r} does not exist; it must be proposed first.")
    if rows[0][0] != "PROPOSED":
        raise ValueError(f"Action {action_id!r} was already {rows[0][0]}; decisions are final.")
    now = _now()
    graph.query(q.DECIDE_ACTION, params={"action_id": action_id, "status": decision, "now": now,
                                         "reviewer": reviewer.strip(), "note": note or ""})
    return {"action_id": action_id, "status": decision, "reviewer": reviewer.strip(), "reviewed_at": now}


def list_actions(graph, incident_id):
    keys = ["action_id", "action_type", "status", "exposure", "target_type", "target_id",
            "rationale", "evidence", "created_at", "reviewed_at", "reviewer", "review_note"]
    rows = graph.ro_query(q.LIST_ACTIONS, params={"incident_id": incident_id}).result_set
    actions = [dict(zip(keys, r)) for r in rows]
    actions.sort(key=lambda a: (_EXPOSURE_ORDER.get(a["exposure"], 9), a["target_id"]))
    return actions
