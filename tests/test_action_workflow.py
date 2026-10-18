"""Pure tests (no database) for the proposal rules."""
import re

from services.action_workflow import propose_actions
from services.impact_assessment import assess
from tests.test_impact_assessment import GAPS, PATHS


def _proposals():
    return propose_actions(assess(["L-204"], PATHS, GAPS), "INC-001")


def test_expected_proposals():
    got = {(p["action_type"], p["target_type"], p["target_id"]) for p in _proposals()}
    assert got == {
        ("QUARANTINE_INVENTORY", "Shipment", "SH-014"),
        ("QUARANTINE_INVENTORY", "Shipment", "SH-015"),
        ("QUARANTINE_INVENTORY", "Shipment", "SH-016"),
        ("PRECAUTIONARY_HOLD", "Shipment", "SH-017"),
        ("ESCALATE_FOR_REVIEW", "Shipment", "SH-019"),
        ("REQUEST_TRACEABILITY_RECORDS", "ProductionBatch", "PR-016"),
    }


def test_all_proposals_start_unapproved_and_ids_are_deterministic():
    ps = _proposals()
    assert all(p["status"] == "PROPOSED" for p in ps)
    assert "INC-001-QUARANTINE_INVENTORY-SH-014" in {p["action_id"] for p in ps}
    assert [p["action_id"] for p in ps] == [p["action_id"] for p in _proposals()]


def test_most_severe_first():
    ranks = [p["exposure"] for p in _proposals()]
    assert ranks[:3] == ["CONFIRMED"] * 3 and ranks[3] == "POTENTIAL"


def test_nothing_proposed_for_unaffected_batch():
    assert not any("PB-040" in p["rationale"] + p["evidence"] or p["target_id"] == "SH-018"
                   for p in _proposals())


def test_requires_incident():
    try:
        propose_actions(assess(["L-204"], PATHS, GAPS), None)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_g_rationale_mentions_only_known_ids():
    known = {"SH-014", "SH-015", "SH-016", "SH-017", "SH-019", "PB-031", "PB-032", "PB-033",
             "PB-034", "PB-050", "PR-016", "PR-012", "PR-013", "PR-015", "L-204", "WH-03",
             "RT-11", "RT-12", "WH-04", "FAC-A"}
    for p in _proposals():
        for tok in re.findall(r"\b[A-Z]{1,3}-[0-9A-Z]+\b", p["rationale"] + " " + p["evidence"]):
            assert tok in known, tok
