"""LLM orchestration loop. The model only chooses tools and writes the explanation; every fact
comes from agent.schemas.dispatch(), i.e. from FalkorDB.

run_agent() works with any session object that has send(text=None, tool_results=None) -> Turn,
so the loop is testable without a model and the provider can be swapped (GeminiSession below).
"""
import sys
import time
from dataclasses import dataclass, field

import config
from agent.prompts import SYSTEM_PROMPT
from agent.schemas import TOOL_SPECS, dispatch, extract_ids


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class Turn:
    text: str = ""
    tool_calls: list = field(default_factory=list)
    blocked: bool = False  # model returned no usable content


@dataclass
class AgentResult:
    answer: str = ""
    tool_trace: list = field(default_factory=list)  # [{"name", "args", "result"}]
    known_ids: set = field(default_factory=set)      # IDs that appeared in tool results
    question_ids: set = field(default_factory=set)   # IDs the user typed
    grounded_by_tools: bool = False
    stopped_early: bool = False
    error: str = None


def run_agent(graph, question, session, dispatcher=dispatch, max_steps=6):
    """Run one question through the tool-calling loop. Never raises."""
    result = AgentResult(question_ids=extract_ids(question))
    try:
        turn = session.send(text=question)
        steps = 0
        while turn.tool_calls:
            if steps >= max_steps:
                result.stopped_early = True
                break
            steps += 1
            outputs = []
            for call in turn.tool_calls:
                out = dispatcher(graph, call.name, call.args)
                result.tool_trace.append({"name": call.name, "args": call.args, "result": out})
                result.known_ids |= extract_ids(out)
                outputs.append((call.name, out))
            turn = session.send(tool_results=outputs)
        result.grounded_by_tools = bool(result.tool_trace)
        result.answer = turn.text
        if turn.blocked or (not turn.text and not result.stopped_early):
            result.error = "The model returned no usable answer. Try rephrasing the question."
        if result.stopped_early:
            result.error = f"Stopped after {max_steps} tool rounds without a final answer."
    except Exception as exc:  # noqa: BLE001 - network/API failures must not crash the UI
        result.error = f"{type(exc).__name__}: {exc}"
    return result


# ---- Gemini adapter ---------------------------------------------------------------------
def gemini_declaration_dicts():
    """Gemini FunctionDeclaration parameters built from our JSON-schema specs (uppercase types)."""
    out = []
    for spec in TOOL_SPECS:
        sch = spec["input_schema"]
        out.append({
            "name": spec["name"],
            "description": spec["description"],
            "parameters": {
                "type": "OBJECT",
                "properties": {k: {"type": "STRING", "description": v.get("description", "")}
                               for k, v in sch["properties"].items()},
                "required": list(sch["required"]),
            },
        })
    return out


class GeminiSession:
    """One conversation with Gemini using manual function calling (google-genai SDK)."""

    def __init__(self, api_key=None, model=None, client=None, retries=2):
        from google import genai
        from google.genai import types

        self._t = types
        key = api_key or config.GEMINI_API_KEY
        if client is None and not key:
            raise RuntimeError("Set GEMINI_API_KEY (or GOOGLE_API_KEY) in your environment.")
        self.client = client or genai.Client(api_key=key)
        self.model = model or config.GEMINI_MODEL
        self.retries = retries
        self.contents = []
        decls = [types.FunctionDeclaration(**d) for d in gemini_declaration_dicts()]
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=decls)],
            temperature=0.2,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def _generate(self):
        last = None
        for attempt in range(self.retries + 1):
            try:
                return self.client.models.generate_content(
                    model=self.model, contents=self.contents, config=self.config)
            except Exception as exc:  # noqa: BLE001 - retry transient errors (429/503)
                last = exc
                if attempt < self.retries:
                    time.sleep(2 * (attempt + 1))
        raise last

    def send(self, text=None, tool_results=None):
        t = self._t
        if text is not None:
            self.contents.append(t.Content(role="user", parts=[t.Part(text=text)]))
        if tool_results:
            parts = [t.Part.from_function_response(name=name, response={"result": res})
                     for name, res in tool_results]
            self.contents.append(t.Content(role="user", parts=parts))
        resp = self._generate()
        cand = resp.candidates[0] if getattr(resp, "candidates", None) else None
        if cand is None or cand.content is None:
            return Turn(blocked=True)
        self.contents.append(cand.content)  # keep the raw model content (needed for later turns)
        calls, texts = [], []
        for part in cand.content.parts or []:
            fc = getattr(part, "function_call", None)
            if fc:
                calls.append(ToolCall(fc.name, dict(fc.args or {})))
            elif getattr(part, "text", None) and not getattr(part, "thought", False):
                texts.append(part.text)
        return Turn(text="".join(texts).strip(), tool_calls=calls)


if __name__ == "__main__":
    from graph.connection import get_graph

    q = sys.argv[1] if len(sys.argv) > 1 else (
        "Investigate L-204. Show affected products and destinations, explain why they are "
        "affected, and prepare a containment plan.")
    res = run_agent(get_graph(), q, GeminiSession())
    for step in res.tool_trace:
        print(f"[tool] {step['name']}({step['args']})")
    print("\n" + (res.answer or "(no answer)"))
    if res.error:
        print(f"\n[error] {res.error}")
