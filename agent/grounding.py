"""Grounding check for LLM answers. Pure Python: no database, no model, no network.

The model may only mention IDs that came out of tool results (i.e. FalkorDB) or that the user
typed. Anything else is flagged as ungrounded so the UI can warn the operator.
This is a guard against invented entities, not a proof that every sentence is correct.
"""
import re
from dataclasses import dataclass, field

from agent.schemas import extract_ids

# Words that must never be asserted about a record just because no path was found.
_SAFE_RE = re.compile(r"\b(?:is|are|was|were|as|be|been|deemed|considered|declared)\s+"
                      r"(?:completely\s+|definitely\s+)?(?:safe|cleared|unaffected)\b", re.I)
_NEGATED_RE = re.compile(r"\b(?:not|never|cannot|can't|nor|isn't|aren't|n't)\b[^.\n]{0,40}$", re.I)


@dataclass
class GroundingReport:
    ungrounded_ids: list = field(default_factory=list)   # in answer, in neither tools nor question
    question_only_ids: list = field(default_factory=list)  # echoed from the question, not verified
    safe_claims: list = field(default_factory=list)      # "is safe" style phrases
    used_tools: bool = True

    @property
    def ok(self):
        return self.used_tools and not self.ungrounded_ids and not self.safe_claims

    def messages(self):
        out = []
        if not self.used_tools:
            out.append("No graph tool was called, so this answer is not backed by FalkorDB.")
        if self.ungrounded_ids:
            out.append("IDs not found in any tool result (possible invention): "
                       + ", ".join(self.ungrounded_ids))
        if self.safe_claims:
            out.append("The answer calls something safe/cleared/unaffected. A missing path is "
                       "not proof of safety: " + "; ".join(self.safe_claims))
        return out


def check_grounding(answer, known_ids, question_ids=(), used_tools=True):
    """Compare IDs in `answer` with the IDs the tools returned. Returns a GroundingReport."""
    known, asked = set(known_ids), set(question_ids)
    mentioned = extract_ids(answer or "")
    claims = []
    for m in _SAFE_RE.finditer(answer or ""):
        before = (answer or "")[max(0, m.start() - 40):m.start()]
        if _NEGATED_RE.search(before):  # "cannot be considered safe" is fine
            continue
        claims.append(m.group(0))
    return GroundingReport(
        ungrounded_ids=sorted(mentioned - known - asked),
        question_only_ids=sorted((mentioned & asked) - known),
        safe_claims=claims,
        used_tools=used_tools,
    )
