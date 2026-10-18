"""Pure tests (no database): the graph picture only contains data from the query results."""
import re

from agent.schemas import extract_ids
from services.impact_assessment import assess
from tests.test_impact_assessment import GAPS, PATHS
from ui.graph_view import build_dot

RESULT = {"found": True, "target": {"lot_ids": ["L-204"]}, "paths": PATHS, "gap_rows": GAPS,
          "assessment": assess(["L-204"], PATHS, GAPS)}
NOT_LINKED_BATCH = {"found": True, "product_batch_id": "PB-040", "verdict": "NOT_LINKED",
                    "producers": [{"production_batch_id": "PR-014", "facility_id": "FAC-B", "lots": ["L-205"]}],
                    "upstream_lots": [{"lot_id": "L-205", "production_batch_id": "PR-014",
                                       "verified": True, "source": "ERP"}]}


def test_every_id_in_the_picture_comes_from_the_results():
    dot = build_dot(RESULT, NOT_LINKED_BATCH)
    allowed = (extract_ids(PATHS) | extract_ids(GAPS) | extract_ids(NOT_LINKED_BATCH))
    assert extract_ids(dot) <= allowed
    assert {"L-204", "PR-012", "PB-031", "SH-014", "WH-03", "PR-016", "PB-050", "SH-019"} <= extract_ids(dot)


def test_unverified_link_is_dashed_and_gap_is_marked():
    dot = build_dot(RESULT)
    line = next(l for l in dot.splitlines() if '"PR-015"' in l and "->" in l and '"L-204"' in l)
    assert "unverified" in line and "dashed" in line
    assert "USED_IN missing" in dot and "no component" in dot


def test_colors_follow_exposure():
    dot = build_dot(RESULT)
    node = lambda n: next(l for l in dot.splitlines() if l.strip().startswith(f'"{n}" ['))
    assert "#F2747A" in node("SH-014") and "#F0A35A" in node("SH-017") and "#E5C65C" in node("SH-019")


def test_comparison_batch_is_drawn_not_linked_and_unaffected_stays_separate():
    dot = build_dot(RESULT, NOT_LINKED_BATCH)
    pb = next(l for l in dot.splitlines() if l.strip().startswith('"PB-040" ['))
    assert "#5FCB8B" in pb
    assert '"L-205" -> "PR-014"' in dot and '"L-204" -> "PR-014"' not in dot


def test_empty_result_and_quote_escaping_do_not_crash():
    empty = {"found": True, "target": {"lot_ids": ["L-1"]}, "paths": [], "gap_rows": [],
             "assessment": assess(["L-1"], [], [])}
    assert build_dot(empty).startswith("digraph")
    odd = [dict(PATHS[0], location_name='North "DC"')]
    dot = build_dot({**RESULT, "paths": odd, "gap_rows": [], "assessment": assess(["L-204"], odd, [])})
    assert '\\"DC\\"' in dot
