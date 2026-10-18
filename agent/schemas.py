"""Provider-independent tool layer for the LLM agent. No LLM or network calls in this module.

Safety design:
  * The agent can investigate, explain and PROPOSE (stored as PROPOSED, simulated).
  * The agent has NO tool to approve or reject. Only a human can, through the UI
    (tools.actions.record_action_decision is deliberately not exposed here).
  * dispatch() validates every argument and never raises: errors come back as {"error": ...}
    so the agent loop can continue.
"""
import json
import re

from services.action_workflow import propose_actions
from tools import actions as act
from tools import investigation as inv

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_ID_TOKEN_RE = re.compile(r"\b[A-Z]{1,3}-[0-9A-Z]+\b")

_ID_PROP = lambda desc: {"type": "string", "description": desc}  # noqa: E731


def _spec(name, description, props):
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": props,
            "required": list(props),
            "additionalProperties": False,
        },
    }


TOOL_SPECS = [
    _spec("resolve_target",
          "Look up an incident ID (e.g. INC-001) or component lot ID (e.g. L-204) in the graph. "
          "Returns the affected lot(s), incident and supplier, or found=false if it does not exist.",
          {"identifier": _ID_PROP("Incident ID or component lot ID")}),
    _spec("investigate_exposure",
          "Trace an incident or component lot through production batches, product batches, shipments "
          "and destinations using graph queries. Returns confirmed, potential and unknown-provenance "
          "findings, each with its evidence path, plus provenance gaps. Call this before making any "
          "claim about what is affected.",
          {"identifier": _ID_PROP("Incident ID or component lot ID")}),
    _spec("explain_product_batch",
          "Explain why a specific product batch is or is not linked to the incident/lot, by tracing "
          "its upstream production batch and component lots. Verdicts: CONFIRMED, POTENTIAL, "
          "UNKNOWN_PROVENANCE (cannot be cleared), NOT_LINKED (no path in recorded provenance).",
          {"product_batch_id": _ID_PROP("Product batch ID, e.g. PB-040"),
           "identifier": _ID_PROP("Incident ID or component lot ID being investigated")}),
    _spec("propose_containment_actions",
          "Prepare simulated containment actions for an incident or lot. Actions are saved as "
          "PROPOSED and wait for a human to approve or reject them in the UI. You cannot approve "
          "or reject them.",
          {"identifier": _ID_PROP("Incident ID or component lot ID")}),
    _spec("list_actions",
          "List the containment actions recorded for an incident with their current status "
          "(PROPOSED, APPROVED or REJECTED).",
          {"incident_id": _ID_PROP("Incident ID, e.g. INC-001")}),
]

SPECS_BY_NAME = {s["name"]: s for s in TOOL_SPECS}
TOOL_NAMES = list(SPECS_BY_NAME)

RULES_REMINDER = (
    "Classification rules: CONFIRMED = verified path from the affected lot; POTENTIAL = path exists "
    "but a record is unverified; UNKNOWN_PROVENANCE = records missing, so the item can be neither "
    "linked nor cleared. Absence of a path is never proof of safety."
)


# ---- provider adapters ----------------------------------------------------------------
def anthropic_tools():
    """Anthropic Messages API format: name, description, input_schema."""
    return [dict(s) for s in TOOL_SPECS]


def openai_tools():
    """OpenAI Chat Completions format."""
    return [{"type": "function",
             "function": {"name": s["name"], "description": s["description"],
                          "parameters": s["input_schema"]}} for s in TOOL_SPECS]


# ---- helpers ------------------------------------------------------------------------
def extract_ids(obj):
    """All ID-like tokens (L-204, PB-031, SH-014, INC-001, FAC-A ...) found in a JSON-able object."""
    return set(_ID_TOKEN_RE.findall(json.dumps(obj, default=str)))


def to_json(result):
    return json.dumps(result, default=str)


def compact_investigation(result):
    """Trim an investigate() result to what the LLM needs, keeping every evidence path."""
    a, t = result["assessment"], result["target"]
    return {
        "found": True,
        "target": {"lot_ids": t["lot_ids"], "incident": t["incident"], "supplier": t.get("supplier")},
        "summary": a["summary"],
        "shipments": [{
            "shipment_id": s["shipment_id"],
            "exposure": s["exposure"],
            "destination": f"{s['location_id']} ({s['location_name']})",
            "product_batches": s["product_batches"],
            "evidence_paths": [e["path_text"] for e in s["evidence"]],
        } for s in a["shipments"]],
        "product_batches": a["product_batches"],
        "locations": a["locations"],
        "provenance_gaps": a["provenance_gaps"],
        "rules": RULES_REMINDER,
    }


# ---- tool handlers ------------------------------------------------------------------
def _resolve(graph, identifier):
    return inv.resolve_target(graph, identifier)


def _investigate(graph, identifier):
    res = inv.investigate(graph, identifier)
    return compact_investigation(res) if res["found"] else {"found": False, "message": res["message"]}


def _explain(graph, product_batch_id, identifier):
    target = inv.resolve_target(graph, identifier)
    if not target["found"]:
        return {"found": False, "message": target["message"]}
    return inv.explain_batch(graph, product_batch_id, target["lot_ids"])


def _propose(graph, identifier):
    res = inv.investigate(graph, identifier)
    if not res["found"]:
        return {"found": False, "message": res["message"]}
    incident = res["target"]["incident"]
    if not incident:
        return {"found": True, "proposals": [],
                "message": "No incident is linked to this lot, so no actions can be proposed."}
    proposals = propose_actions(res["assessment"], incident["incident_id"])
    act.persist_proposals(graph, incident["incident_id"], proposals)
    return {
        "found": True,
        "incident_id": incident["incident_id"],
        "note": "Actions are SIMULATED and saved as PROPOSED. A human must approve or reject them in "
                "the UI; you cannot.",
        "proposals": [{k: p[k] for k in ("action_id", "action_type", "exposure", "target_type",
                                         "target_id", "rationale", "evidence")} for p in proposals],
    }


def _list_actions(graph, incident_id):
    actions = act.list_actions(graph, incident_id)
    return {"incident_id": incident_id, "actions": [
        {k: a[k] for k in ("action_id", "action_type", "status", "exposure", "target_type",
                           "target_id", "reviewer", "reviewed_at")} for a in actions]}


HANDLERS = {
    "resolve_target": _resolve,
    "investigate_exposure": _investigate,
    "explain_product_batch": _explain,
    "propose_containment_actions": _propose,
    "list_actions": _list_actions,
}


# ---- dispatcher ---------------------------------------------------------------------
def _validate(spec, arguments):
    schema = spec["input_schema"]
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be a JSON object")
    extra = set(arguments) - set(schema["properties"])
    if extra:
        raise ValueError(f"unexpected arguments: {sorted(extra)}")
    for key in schema["required"]:
        if key not in arguments:
            raise ValueError(f"missing required argument: {key}")
    for key, value in arguments.items():
        if not isinstance(value, str) or not _ID_RE.match(value.strip()):
            raise ValueError(f"{key} must be an identifier string such as 'L-204'")


def dispatch(graph, name, arguments):
    """Run one tool call. Always returns a JSON-serialisable dict; never raises."""
    spec = SPECS_BY_NAME.get(name)
    if spec is None:
        return {"error": f"Unknown tool {name!r}. Available tools: {TOOL_NAMES}"}
    try:
        _validate(spec, arguments)
        args = {k: v.strip() for k, v in arguments.items()}
        return HANDLERS[name](graph, **args)
    except (ValueError, LookupError) as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - database or unexpected failure, keep the loop alive
        return {"error": f"Tool {name} failed: {type(exc).__name__}: {exc}"}
