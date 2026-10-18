# TraceBack

**Graph-powered supply-chain containment agent.**
Built for the WeMakeDevs x FalkorDB **Graph Hacks 2026**, **Track 1: Agents That Act on Connected Data**.

> Trace the incident. Prove the impact. Contain what is affected. Make uncertainty visible. Explain every action.

A supplier reports that component lot **L-204** is contaminated. TraceBack traverses a FalkorDB graph
(lot -> production batch -> product batch -> shipment -> location), separates **confirmed**,
**potential** and **unknown-provenance** exposure, proposes targeted containment actions, and waits
for a **human** to approve or reject each one. Every finding comes with its evidence path.

- All data is **synthetic demo data**. Nothing connects to a real manufacturer or carrier.
- All containment actions are **simulated**. No real hold, recall or quarantine happens.
- An action cannot be approved by the AI. Only a named human reviewer can, through the UI.

Demo video: _TODO: add link_ | Live deployment: none, run locally (see Setup)

---

## What it does

| Question | How TraceBack answers it |
|---|---|
| What is affected? | 4-hop Cypher traversal in FalkorDB from the affected lot to shipments and destinations |
| How do we know? | Every row is one complete path; the app prints it (`L-204 -[USED_IN]-> PR-012 -[PRODUCED]-> ...`) |
| What should we do? | Rule-based action proposals, saved as `PROPOSED` in the graph |
| What remains unknown? | A provenance-gap query finds batches with no recorded components. They are never called safe |

The graph is essential: the affected set comes from graph traversal, not from a precomputed list,
an in-memory structure, or an LLM guess.

## Architecture

```text
Streamlit UI  --->  Agent (Gemini, optional)  --->  Tool layer (validated, no free-form Cypher)
     |                      |                                  |
     |                      +-- grounding check                v
     +----------------------------------------------->  FalkorDB graph
                                                       (data + action audit trail)
```

- `app.py`: Streamlit UI (investigation, evidence, approvals, "Ask TraceBack").
- `agent/`: LLM tool-calling loop (`orchestrator.py`), prompt (`prompts.py`), tool specs and
  dispatcher (`schemas.py`), answer grounding check (`grounding.py`).
- `tools/`, `services/`: investigation, impact classification, action workflow.
- `graph/`: connection, seed data, and **all Cypher** (`queries.py`).

The UI works **without** the LLM. The LLM only chooses among five predefined tools and explains their output.

## Setup

Requirements: Docker, Python 3.9+.

```bash
git clone https://github.com/vikrantraj2004/traceback-graph-hacks.git
cd traceback-graph-hacks
docker compose up -d                                  # FalkorDB on localhost:6379
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m graph.seed_data                             # expects: 28 nodes, 28 relationships
python -m tools.investigation L-204                   # CLI investigation
streamlit run app.py                                  # UI at http://localhost:8501
pytest -v                                             # DB tests use a separate 'traceback_test' graph
```

Optional "Ask TraceBack" agent (Google Gemini). Set real environment variables; `.env` files are not read:

```bash
export GEMINI_API_KEY=your-key                        # PowerShell: $env:GEMINI_API_KEY="your-key"
export GEMINI_MODEL=gemini-flash-latest               # optional; change if the model is unavailable
python -m agent.orchestrator                          # CLI agent run
```

Other settings: `FALKORDB_HOST`, `FALKORDB_PORT`, `TRACEBACK_GRAPH` (default `traceback_demo`).

## Demo walkthrough

1. Open the app, keep `L-204`, click **Investigate**.
2. **Shipments & destinations**: confirmed SH-014, SH-015, SH-016; potential SH-017; unknown SH-019. Open an evidence expander.
3. **Provenance gaps**: PR-016 has no recorded components, so SH-019 is flagged, not cleared.
4. **Why (not) affected?**: PB-040 is not linked (built from L-205); PB-050 is unknown provenance and cannot be cleared.
5. **Actions & audit trail**: enter your name in the sidebar, approve or reject a proposed action.
6. **Ask TraceBack** (needs `GEMINI_API_KEY`): ask the same question in natural language. The answer is checked against the tool results.

## Graph model

```text
(Supplier)-[:SUPPLIED]->(ComponentLot)<-[:AFFECTS]-(Incident)
(ComponentLot)-[:USED_IN {verified, source}]->(ProductionBatch)
(ProductionBatch)-[:PRODUCED]->(ProductBatch)
(ProductBatch)-[:INCLUDED_IN {quantity}]->(Shipment)-[:DELIVERED_TO]->(Location)
(Incident)-[:TRIGGERED]->(ContainmentAction)-[:TARGETS]->(Shipment | ProductBatch | Location | ProductionBatch)
```

| Node | Key properties |
|---|---|
| Supplier | supplier_id, name, status |
| ComponentLot | lot_id, component_name, status, provenance_status |
| Incident | incident_id, incident_type, description, severity, status, reported_at |
| ProductionBatch | production_batch_id, facility_id, produced_at, components_recorded |
| ProductBatch | product_batch_id, product_name, provenance_status |
| Shipment | shipment_id, dispatch_date, status |
| Location | location_id, name, location_type, region |
| ContainmentAction | action_id, action_type, status, exposure, rationale, evidence, created_at, reviewed_at, reviewer, simulated |

Edge properties that carry meaning:
- `USED_IN.verified` (true/false) and `USED_IN.source` (e.g. "ERP batch record" vs "handwritten line log"): drives confirmed vs potential.
- `INCLUDED_IN.quantity`: units of a product batch in a shipment.

The seed data (`graph/seed_data.py`) has 28 nodes and 28 relationships, with branching paths, a shared
destination (WH-04), a decoy batch from another lot (PB-040 from L-205), an unverified link (PR-015),
and a production batch with no recorded components (PR-016).

## Key Cypher queries

All Cypher is in [`graph/queries.py`](graph/queries.py) and is parameterised. The agent cannot send its own Cypher.

**1. Multi-hop impact trace with evidence (4 hops).** One row is one complete path;
`rel_types` is read from the matched path so the app can check the shape FalkorDB returned.

```cypher
MATCH p = (l:ComponentLot)-[u:USED_IN]->(pr:ProductionBatch)-[:PRODUCED]->(pb:ProductBatch)
          -[inc:INCLUDED_IN]->(s:Shipment)-[:DELIVERED_TO]->(loc:Location)
WHERE l.lot_id IN $lot_ids
RETURN l.lot_id AS lot_id, pr.production_batch_id AS production_batch_id,
       pb.product_batch_id AS product_batch_id, s.shipment_id AS shipment_id,
       loc.location_id AS location_id, loc.name AS location_name,
       u.verified AS verified, u.source AS source, inc.quantity AS quantity,
       [r IN relationships(p) | type(r)] AS rel_types
ORDER BY shipment_id, product_batch_id, lot_id
```
For `L-204` this returns 5 paths (SH-014, SH-015 x2, SH-016, SH-017).

**2. Provenance gaps.** Production batches at the same facility as an affected batch that have
no incoming `USED_IN`. The graph can neither link them to the incident nor clear them.

```cypher
MATCH (l:ComponentLot)-[:USED_IN]->(apr:ProductionBatch)
WHERE l.lot_id IN $lot_ids
WITH collect(DISTINCT apr.facility_id) AS facilities
MATCH (pr:ProductionBatch)
WHERE pr.facility_id IN facilities
OPTIONAL MATCH (c:ComponentLot)-[u:USED_IN]->(pr)
WITH pr, count(u) AS recorded
WHERE recorded = 0
OPTIONAL MATCH (pr)-[:PRODUCED]->(pb:ProductBatch)
OPTIONAL MATCH (pb)-[inc:INCLUDED_IN]->(s:Shipment)
OPTIONAL MATCH (s)-[:DELIVERED_TO]->(loc:Location)
RETURN pr.production_batch_id AS production_batch_id, pr.facility_id AS facility_id,
       pb.product_batch_id AS product_batch_id, s.shipment_id AS shipment_id,
       loc.location_id AS location_id, loc.name AS location_name, inc.quantity AS quantity
```
For `L-204` this returns 1 row: PR-016 -> PB-050 -> SH-019 -> WH-04.

**3. Why (not) affected?** Walks upstream from a product batch to its recorded component lots.

```cypher
MATCH (pb:ProductBatch {product_batch_id: $product_batch_id})
OPTIONAL MATCH (pr:ProductionBatch)-[:PRODUCED]->(pb)
OPTIONAL MATCH (l:ComponentLot)-[u:USED_IN]->(pr)
RETURN pb.product_batch_id AS product_batch_id, pr.production_batch_id AS production_batch_id,
       pr.facility_id AS facility_id, l.lot_id AS lot_id, u.verified AS verified, u.source AS source
```

**4. Resolve the starting entity / 2-hop trace.** `GET_LOT_CONTEXT`, `GET_INCIDENT_LOTS` and
`TRACE_AFFECTED_BATCHES` use `OPTIONAL MATCH` so "lot not found" (zero rows) differs from
"lot found, nothing downstream" (one row of nulls).

**5. Audit trail.** Proposals are idempotent (`ON CREATE SET`), so re-investigating never overwrites a
decided action. Decisions record the reviewer and time.

```cypher
// propose
MATCH (i:Incident {incident_id: $incident_id})
MERGE (a:ContainmentAction {action_id: $action_id})
ON CREATE SET a.status = 'PROPOSED', a.action_type = $action_type, a.exposure = $exposure,
              a.target_type = $target_type, a.target_id = $target_id, a.rationale = $rationale,
              a.evidence = $evidence, a.created_at = $now, a.simulated = true
MERGE (i)-[:TRIGGERED]->(a)

// decide (only called with a named human reviewer)
MATCH (a:ContainmentAction {action_id: $action_id})
SET a.status = $status, a.reviewed_at = $now, a.reviewer = $reviewer, a.review_note = $note
```
Each action is also linked with `(a)-[:TARGETS]->(target)`. Target labels come from a fixed whitelist.

## Exposure rules

Implemented in `services/impact_assessment.py`:

| Class | Rule |
|---|---|
| CONFIRMED | a path from the affected lot exists and its `USED_IN` edge has `verified = true` |
| POTENTIAL | a path exists but `verified` is false or missing |
| UNKNOWN_PROVENANCE | production batch at an affected facility with no recorded components |
| NOT_LINKED | no path in recorded provenance. This is **not** "safe" |

Precedence when a shipment or location is reached several ways: CONFIRMED > POTENTIAL > UNKNOWN_PROVENANCE.

Expected result for `L-204`:

| Shipment | Destination | Class |
|---|---|---|
| SH-014 | WH-03 | CONFIRMED |
| SH-015 | RT-11 | CONFIRMED |
| SH-016 | RT-12 | CONFIRMED |
| SH-017 | WH-04 | POTENTIAL (PR-015 link is a handwritten log, unverified) |
| SH-019 | WH-04 | UNKNOWN_PROVENANCE (PR-016 has no recorded components) |

SH-018 (PB-040, built from L-205) is not linked. 6 simulated actions are proposed.

## Safety and honesty design

- **No free-form Cypher.** The LLM picks from five tools with validated ID arguments (`agent/schemas.py`).
- **The agent cannot approve or reject.** There is no such tool; only the UI calls `record_action_decision`, and it requires a reviewer name.
- **Decisions are final** and stored in the graph with reviewer and timestamp.
- **Tool output is treated as data**, not instructions (prompt rule).
- **Grounding check** (`agent/grounding.py`): any ID in an answer that is not in a tool result or your question is flagged; "is safe/cleared" claims are flagged; answers with no tool call are flagged. This catches invented entities and unsafe wording; it does not prove every sentence is correct.

## Tests

```bash
pytest -v
```

- No database needed: classification rules, action workflow, tool schemas and dispatcher validation,
  orchestrator loop (scripted fake model), grounding check.
- Needs FalkorDB (uses the `traceback_test` graph, never your demo graph): seed counts, 2-hop and
  4-hop queries (exactly 5 paths for L-204), provenance-gap query (exactly 1 row), unknown lot,
  invalid ID, unaffected comparison (PB-040), action persistence and the approval gate, agent dispatch.
- The Gemini call itself is not covered by automated tests (it needs a key and network); it is checked manually.

## Project layout

```text
app.py                      Streamlit UI
config.py                   environment settings
graph/                      connection.py, seed_data.py, queries.py (all Cypher)
tools/                      investigation.py, actions.py
services/                   impact_assessment.py, action_workflow.py
agent/                      orchestrator.py, prompts.py, schemas.py, grounding.py
tests/                      pytest suite
docker-compose.yml          FalkorDB
```

## Limitations

- Synthetic data only; the dataset is tiny by design so results can be checked by hand.
- Actions are simulated; nothing is sent to any real system.
- Provenance-gap detection is facility-based: it looks at production batches with no recorded components at facilities that processed the affected lot.
- No authentication: the reviewer name is a free-text field, not a verified identity.
- The LLM layer uses Google Gemini; the tool layer is provider-independent (Anthropic and OpenAI tool formats exist in `agent/schemas.py`).

## AI assistant disclosure

Claude (Anthropic) was used as a coding assistant for design, code, tests and documentation; Google
Gemini is the runtime LLM for the optional agent. Details: [ARCHITECTURE.md](ARCHITECTURE.md#8-ai-assistant-usage-disclosure).
