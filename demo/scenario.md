# TraceBack demo scenario and recording checklist

Target length: about 3 minutes. All data is synthetic; say so once at the start.

## Before you record (5 minutes)

- [ ] `docker compose up -d` and confirm the container is running
- [ ] `python -m graph.seed_data` prints 28 nodes, 28 relationships
- [ ] `pytest -v` is green (optionally show this for 5 seconds)
- [ ] `GEMINI_API_KEY` is set in the same terminal that runs `streamlit run app.py`
- [ ] `streamlit run app.py`, then click **Reset demo data** so every action starts as PROPOSED
- [ ] Do one dry run of the "Ask TraceBack" question to confirm the model works. If it fails, see "If something goes wrong"
- [ ] Browser zoom 110-125%, close other tabs, silence notifications
- [ ] Type your name in the sidebar **Reviewer** field only when you reach the approval step, so the disabled buttons are visible first
- [ ] Screen recorder on, microphone tested, window large enough to read evidence paths

## Script

### 0:00 - 0:20 The problem

Show the app title.

> "A supplier reports lot L-204 is contaminated. Which products and destinations are affected, how do we know, and what should we do? The records are connected across five levels, so TraceBack follows them in a FalkorDB graph. The data is synthetic and every action is simulated."

### 0:20 - 1:00 Investigate

Type `L-204`, click **Investigate**.

> "TraceBack resolves the lot to incident INC-001 and supplier S-17, then runs a four-hop Cypher query in FalkorDB: lot, production batch, product batch, shipment, location."

Point at the metrics: 3 confirmed, 1 potential, 1 unknown-provenance shipment, 1 provenance gap.

The **Graph** tab opens first. Pause on it for a few seconds.

> "This is the traversal made visible: L-204 fans out through production batches and product batches to shipments and destinations. Red is confirmed, orange is potential, yellow is unknown. The dashed line is an unverified record, and the grey box is a record that doesn't exist. PB-040 on top comes from a different lot, so it's separate."

Open the **Shipments & destinations** tab, then open the evidence expander for SH-014.

> "Every finding is a real graph path. SH-014 is confirmed: L-204 was used in PR-012 with a verified ERP record, which produced PB-031, shipped in SH-014 to WH-03."

Open the SH-017 evidence.

> "SH-017 is only potential: the link from L-204 to PR-015 comes from a handwritten log and is unverified. We don't treat it as confirmed."

### 1:00 - 1:40 Uncertainty and the unaffected comparison

Open **Provenance gaps**.

> "PR-016 has no recorded components. The graph can neither link it to the incident nor clear it, so SH-019 is flagged for review. Missing data is shown as uncertainty, never as safe."

Open **Why (not) affected?** and select **PB-040**.

> "PB-040 was built from lot L-205, so it is not linked, and TraceBack shows that path instead of hiding it. Targeted containment, not a blanket recall."

Select **PB-050**.

> "PB-050 has incomplete provenance. It cannot be cleared."

### 1:40 - 2:20 Actions and human approval

Open **Actions & audit trail**. Show the 6 PROPOSED actions.

> "Each action has a rationale and its evidence path. Quarantine for confirmed shipments, a precautionary hold for the potential one, escalation for the unknown one, and a request for traceability records for PR-016."

Point at the disabled Approve/Reject buttons.

> "Nobody can approve anonymously."

Type your name in the sidebar, approve one action, reject another.

> "The decision, reviewer and timestamp are written back to the graph. Decisions are final."

### 2:20 - 2:50 Ask TraceBack (the agent)

Scroll to **Ask TraceBack**, click **Ask** with the default question.

> "The same investigation in natural language. Gemini chooses graph tools; it cannot run its own Cypher, and it has no tool to approve actions."

Open the **Tool calls** expander, then point at the green grounding line.

> "Every ID in this answer appears in a tool result from FalkorDB. If the model invented one, or called something safe, we would flag it."

Optional if time allows: ask "Is PB-040 safe?" and show that the answer says it is not linked, not that it is safe.

### 2:50 - 3:00 Close

> "Trace the incident, prove the impact, contain what is affected, make uncertainty visible, and explain every action. Code, queries and setup are in the README."

## If something goes wrong

| Problem | Fix |
|---|---|
| "Cannot reach FalkorDB" | `docker compose up -d`, reload the page |
| Actions already show APPROVED | Click **Reset demo data**, then **Investigate** again |
| Gemini error or empty answer | Click Ask again; if it persists, set `GEMINI_MODEL` (for example `gemini-3.5-flash`) and restart Streamlit. Otherwise skip that section; the rest works without the LLM |
| Answer wording differs between takes | Normal. Make sure the facts match: SH-014/015/016 confirmed, SH-017 potential, SH-019 needs review |
| Grounding warning appears | Don't hide it. Explain that the check flagged an ID not in tool results, then ask again |

## After recording

- [ ] Watch it once: evidence paths readable, no API key or personal data visible on screen
- [ ] Upload (YouTube unlisted or similar) and paste the link into the README ("Demo video: TODO")
- [ ] Confirm the repository is public and the README setup steps work from a clean clone
- [ ] Check the official rules page for any submission requirement not covered here:
      https://www.wemakedevs.org/hackathons/falkordb/rules
- [ ] Do not claim live deployment; the project runs locally
