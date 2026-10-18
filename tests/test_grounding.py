"""Pure tests (no database, no Gemini) for the answer grounding check."""
from agent.grounding import check_grounding

KNOWN = {"L-204", "PR-012", "PB-031", "SH-014", "WH-03", "INC-001"}


def test_answer_using_only_tool_ids_is_ok():
    r = check_grounding("SH-014 carries PB-031 from PR-012 (lot L-204), delivered to WH-03.", KNOWN, {"L-204"})
    assert r.ok and r.messages() == []


def test_invented_id_is_flagged():
    r = check_grounding("SH-014 and SH-099 are affected.", KNOWN, {"L-204"})
    assert r.ungrounded_ids == ["SH-099"] and not r.ok
    assert "SH-099" in r.messages()[0]


def test_id_only_in_question_is_allowed_but_reported_unverified():
    r = check_grounding("PB-999 was not found in the graph.", KNOWN, {"PB-999"})
    assert r.ungrounded_ids == [] and r.question_only_ids == ["PB-999"] and r.ok


def test_no_tool_call_is_not_ok():
    r = check_grounding("Which lot?", set(), set(), used_tools=False)
    assert not r.ok and "No graph tool" in r.messages()[0]


def test_safe_claim_is_flagged():
    r = check_grounding("PB-040 is safe because no path was found.", KNOWN | {"PB-040"})
    assert r.safe_claims and not r.ok


def test_negated_safe_wording_is_not_flagged():
    r = check_grounding("PB-050 cannot be considered safe; it needs review.", KNOWN | {"PB-050"})
    assert r.safe_claims == [] and r.ok


def test_empty_answer_does_not_crash():
    assert check_grounding("", KNOWN).ungrounded_ids == []
    assert check_grounding(None, KNOWN).ungrounded_ids == []
