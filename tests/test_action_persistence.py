"""Database tests for the approval workflow (test F). Need FalkorDB running."""
import pytest

from graph import queries as q
from services.action_workflow import propose_actions
from tools.actions import list_actions, persist_proposals, record_action_decision
from tools.investigation import investigate


def _setup(g):
    res = investigate(g, "L-204")
    props = propose_actions(res["assessment"], "INC-001")
    persist_proposals(g, "INC-001", props)
    return props


def _count_actions(g):
    return g.ro_query("MATCH (a:ContainmentAction) RETURN count(a)").result_set[0][0]


def test_proposals_are_persisted_unapproved_and_idempotent(fresh_graph):
    props = _setup(fresh_graph)
    acts = list_actions(fresh_graph, "INC-001")
    assert len(acts) == len(props) == 6
    assert all(a["status"] == "PROPOSED" and a["reviewer"] is None for a in acts)
    persist_proposals(fresh_graph, "INC-001", props)  # run again
    assert _count_actions(fresh_graph) == 6


def test_graph_edges_for_audit_trail(fresh_graph):
    _setup(fresh_graph)
    n = fresh_graph.ro_query(
        "MATCH (:Incident {incident_id:'INC-001'})-[:TRIGGERED]->(a:ContainmentAction)-[:TARGETS]->(t) "
        "RETURN count(a)").result_set[0][0]
    assert n == 6


def test_f_approve_records_reviewer_and_timestamp(fresh_graph):
    _setup(fresh_graph)
    aid = "INC-001-QUARANTINE_INVENTORY-SH-014"
    out = record_action_decision(fresh_graph, aid, "approved", "A. Reviewer", "looks right")
    assert out["status"] == "APPROVED"
    a = {x["action_id"]: x for x in list_actions(fresh_graph, "INC-001")}[aid]
    assert a["status"] == "APPROVED" and a["reviewer"] == "A. Reviewer" and a["reviewed_at"]


def test_f_reject_is_recorded(fresh_graph):
    _setup(fresh_graph)
    aid = "INC-001-PRECAUTIONARY_HOLD-SH-017"
    record_action_decision(fresh_graph, aid, "REJECTED", "A. Reviewer", "records verified")
    a = {x["action_id"]: x for x in list_actions(fresh_graph, "INC-001")}[aid]
    assert a["status"] == "REJECTED"


@pytest.mark.parametrize("decision,reviewer", [("APPROVED", ""), ("APPROVED", None), ("MAYBE", "X"), (None, "X")])
def test_f_cannot_approve_without_valid_decision_and_reviewer(fresh_graph, decision, reviewer):
    _setup(fresh_graph)
    aid = "INC-001-QUARANTINE_INVENTORY-SH-014"
    with pytest.raises(ValueError):
        record_action_decision(fresh_graph, aid, decision, reviewer)
    a = {x["action_id"]: x for x in list_actions(fresh_graph, "INC-001")}[aid]
    assert a["status"] == "PROPOSED"


def test_f_unknown_action_and_double_decision(fresh_graph):
    _setup(fresh_graph)
    with pytest.raises(LookupError):
        record_action_decision(fresh_graph, "INC-001-NOPE-SH-999", "APPROVED", "X")
    aid = "INC-001-QUARANTINE_INVENTORY-SH-015"
    record_action_decision(fresh_graph, aid, "APPROVED", "X")
    with pytest.raises(ValueError):
        record_action_decision(fresh_graph, aid, "REJECTED", "X")


def test_unknown_incident_or_target_writes_nothing(fresh_graph):
    props = propose_actions(investigate(fresh_graph, "L-204")["assessment"], "INC-001")
    with pytest.raises(ValueError):
        persist_proposals(fresh_graph, "INC-999", props)
    bad = dict(props[0], target_id="SH-999", action_id="INC-001-X-SH-999")
    with pytest.raises(ValueError):
        persist_proposals(fresh_graph, "INC-001", props + [bad])
    assert _count_actions(fresh_graph) == 0


def test_dynamic_target_labels_are_whitelisted():
    with pytest.raises(KeyError):
        q.target_exists_query("Shipment) DETACH DELETE (n")
