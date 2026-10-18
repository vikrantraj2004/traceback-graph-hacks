"""Pure tests (no database, no LLM) for the agent tool layer."""
import json

from agent import schemas as s
from services.impact_assessment import assess
from tests.test_impact_assessment import GAPS, PATHS


def test_specs_are_well_formed():
    names = [t["name"] for t in s.TOOL_SPECS]
    assert len(names) == len(set(names)) == 5
    for t in s.TOOL_SPECS:
        sch = t["input_schema"]
        assert t["description"] and sch["type"] == "object"
        assert set(sch["required"]) <= set(sch["properties"])
        assert sch["additionalProperties"] is False


def test_agent_has_no_approval_tool():
    assert "record_action_decision" not in s.TOOL_NAMES
    assert not any(w in n for n in s.TOOL_NAMES for w in ("approve", "reject", "decision"))
    assert "error" in s.dispatch(None, "record_action_decision", {"action_id": "x"})


def test_dispatch_rejects_bad_arguments_before_touching_the_database():
    # graph=None proves validation happens first; any DB access would raise AttributeError.
    assert "error" in s.dispatch(None, "investigate_exposure", {})
    assert "error" in s.dispatch(None, "investigate_exposure", {"identifier": "x; DROP"})
    assert "error" in s.dispatch(None, "investigate_exposure", {"identifier": "L-204", "extra": "1"})
    assert "error" in s.dispatch(None, "investigate_exposure", {"identifier": 204})
    assert "error" in s.dispatch(None, "investigate_exposure", "L-204")
    assert "error" in s.dispatch(None, "no_such_tool", {})


def test_provider_adapters():
    a = s.anthropic_tools()
    assert all({"name", "description", "input_schema"} <= set(t) for t in a)
    o = s.openai_tools()
    assert all(t["type"] == "function" and t["function"]["parameters"]["type"] == "object" for t in o)
    assert [t["function"]["name"] for t in o] == s.TOOL_NAMES


def test_extract_ids():
    ids = s.extract_ids({"x": "L-204 -[USED_IN]-> PR-012", "y": ["SH-014", "FAC-A", "INC-001"]})
    assert ids == {"L-204", "PR-012", "SH-014", "FAC-A", "INC-001"}


def test_compact_investigation_keeps_evidence_and_is_json_safe():
    assessment = assess(["L-204"], PATHS, GAPS)
    result = {"found": True, "assessment": assessment,
              "target": {"lot_ids": ["L-204"], "incident": {"incident_id": "INC-001"}, "supplier": None}}
    out = s.compact_investigation(result)
    json.dumps(out)  # must serialise
    assert out["summary"]["confirmed_shipments"] == 3
    by_id = {x["shipment_id"]: x for x in out["shipments"]}
    assert by_id["SH-014"]["evidence_paths"][0].startswith("L-204 -[USED_IN")
    assert len(by_id["SH-015"]["evidence_paths"]) == 2
    assert out["provenance_gaps"][0]["production_batch_id"] == "PR-016"
    assert "never proof of safety" in out["rules"]
    assert "PB-040" not in s.extract_ids(out)
