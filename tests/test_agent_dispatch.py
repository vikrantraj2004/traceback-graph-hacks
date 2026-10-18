"""Database tests for the agent tool dispatcher. Need FalkorDB running."""
from agent import schemas as s
from tools.actions import list_actions


def test_investigate_exposure_l204(graph):
    out = s.dispatch(graph, "investigate_exposure", {"identifier": "L-204"})
    assert out["found"] and out["summary"]["confirmed_shipments"] == 3
    assert out["summary"]["unknown_shipments"] == 1
    assert all(sh["evidence_paths"] for sh in out["shipments"])


def test_unknown_identifier_is_a_controlled_response(graph):
    out = s.dispatch(graph, "investigate_exposure", {"identifier": "L-999"})
    assert out["found"] is False and "error" not in out


def test_explain_product_batch(graph):
    out = s.dispatch(graph, "explain_product_batch", {"product_batch_id": "PB-040", "identifier": "L-204"})
    assert out["verdict"] == "NOT_LINKED"
    out = s.dispatch(graph, "explain_product_batch", {"product_batch_id": "PB-050", "identifier": "INC-001"})
    assert out["verdict"] == "UNKNOWN_PROVENANCE"


def test_propose_saves_proposed_only_and_agent_cannot_approve(fresh_graph):
    out = s.dispatch(fresh_graph, "propose_containment_actions", {"identifier": "L-204"})
    assert out["found"] and len(out["proposals"]) == 6
    acts = list_actions(fresh_graph, "INC-001")
    assert len(acts) == 6 and all(a["status"] == "PROPOSED" for a in acts)
    listed = s.dispatch(fresh_graph, "list_actions", {"incident_id": "INC-001"})
    assert all(a["status"] == "PROPOSED" for a in listed["actions"])


def test_lot_without_incident_proposes_nothing(fresh_graph):
    out = s.dispatch(fresh_graph, "propose_containment_actions", {"identifier": "L-205"})
    assert out["proposals"] == []
