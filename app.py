"""TraceBack Streamlit UI. Synthetic demo data; all actions are simulated."""
import streamlit as st

import config
from agent.grounding import check_grounding
from agent.orchestrator import GeminiSession, run_agent
from graph.connection import get_graph
from graph.seed_data import seed
from services.action_workflow import propose_actions
from tools import actions as act
from ui.graph_view import LEGEND, build_dot
from ui.style import chip, header, inject_css, pill
from tools.investigation import explain_batch, investigate, list_product_batches

st.set_page_config(page_title="TraceBack", page_icon="◼", layout="wide")
inject_css()

BADGE = {"CONFIRMED": "🔴 CONFIRMED", "POTENTIAL": "🟠 POTENTIAL",
         "UNKNOWN_PROVENANCE": "🟡 UNKNOWN PROVENANCE", "NOT_LINKED": "🟢 NOT LINKED",
         "PROPOSED": "⏳ PROPOSED", "APPROVED": "✅ APPROVED", "REJECTED": "⛔ REJECTED"}


@st.cache_resource
def graph_handle():
    return get_graph()


header("TraceBack", "Graph-powered supply-chain containment. Synthetic demo data. "
       "All actions are simulated and require human approval.")

try:
    graph = graph_handle()
    graph.ro_query("RETURN 1")
except Exception as exc:  # noqa: BLE001
    st.error("Cannot reach FalkorDB. Start it with `docker compose up -d`, then reload.")
    st.code(str(exc))
    st.stop()

with st.sidebar:
    st.header("Reviewer")
    reviewer = st.text_input("Your name (required to approve/reject)", key="reviewer")
    st.divider()
    if st.button("Reset demo data"):
        seed(graph)
        st.session_state.pop("result", None)
        st.rerun()

st.subheader("Ask TraceBack")
st.caption("An LLM chooses graph tools and explains their output. It cannot approve actions, "
           "and any ID it mentions that is not in a tool result is flagged.")
if not config.GEMINI_API_KEY:
    st.info("Set GEMINI_API_KEY in the environment that launches Streamlit to enable this box. "
            "The investigation below works without it.")
else:
    with st.form("ask_form"):
        question = st.text_area(
            "Question", height=80,
            value="Investigate L-204. Show affected products and destinations, explain why they "
                  "are affected, and prepare a containment plan.")
        asked = st.form_submit_button("Ask")
    if asked and question.strip():
        with st.spinner("Querying the graph..."):
            try:
                res = run_agent(graph, question.strip(), GeminiSession())
                st.session_state["ask"] = (res, check_grounding(
                    res.answer, res.known_ids, res.question_ids, res.grounded_by_tools))
            except Exception as exc:  # noqa: BLE001 - e.g. missing SDK
                st.session_state["ask"] = None
                st.error(f"{type(exc).__name__}: {exc}")
    saved = st.session_state.get("ask")
    if saved:
        res, report = saved
        if res.error:
            st.error(res.error)
        if res.answer:
            st.markdown(res.answer)
        for msg in report.messages():
            st.warning(msg)
        if res.answer and report.ok:
            st.success(f"Grounding check passed: every ID in the answer appears in "
                       f"{len(res.tool_trace)} tool result(s) from FalkorDB.")
        if report.question_only_ids:
            st.caption("Not verified by the graph (echoed from your question): "
                       + ", ".join(report.question_only_ids))
        with st.expander(f"Tool calls ({len(res.tool_trace)})"):
            for step in res.tool_trace:
                st.code(f"{step['name']}({step['args']})", language=None)
                st.json(step["result"], expanded=False)
        if any(t["name"] == "propose_containment_actions" for t in res.tool_trace):
            st.info("Actions were proposed (simulated). Review them in the Actions & audit trail tab "
                    "after running Investigate for the same lot.")
st.divider()

ident = st.text_input("Incident or component lot ID", value="L-204",
                      help="e.g. L-204, L-205, INC-001")
if st.button("Investigate", type="primary"):
    try:
        result = investigate(graph, ident)
        st.session_state["result"] = result
        incident = result["target"]["incident"] if result["found"] else None
        if incident:
            props = propose_actions(result["assessment"], incident["incident_id"])
            act.persist_proposals(graph, incident["incident_id"], props)
    except ValueError as exc:
        st.session_state.pop("result", None)
        st.error(str(exc))

result = st.session_state.get("result")
if not result:
    st.info("Enter an ID and click Investigate.")
    st.stop()
if not result["found"]:
    st.warning(result["message"])
    st.stop()

target, a = result["target"], result["assessment"]
incident = target["incident"]

st.subheader("Starting point")
c1, c2, c3 = st.columns(3)
c1.metric("Lot(s)", ", ".join(target["lot_ids"]))
c2.metric("Incident", incident["incident_id"] if incident else "none linked")
c3.metric("Supplier", target["supplier"]["supplier_id"] if target.get("supplier") else "-")
if incident:
    st.write(f"**{incident['severity']}**: {incident['description']}")
else:
    st.warning("No incident is linked to this lot, so actions cannot be recorded.")

s = a["summary"]
st.subheader("Impact")
m = st.columns(4)
m[0].metric("Confirmed shipments", s["confirmed_shipments"])
m[1].metric("Potential shipments", s["potential_shipments"])
m[2].metric("Unknown-provenance shipments", s["unknown_shipments"])
m[3].metric("Provenance gaps", s["provenance_gaps"])

tab_graph, tab_ship, tab_gap, tab_why, tab_act = st.tabs(
    ["Graph", "Shipments & destinations", "Provenance gaps", "Why (not) affected?", "Actions & audit trail"])

with tab_graph:
    st.caption("Drawn from the FalkorDB query results for this investigation. Dashed orange edges are "
               "unverified records; the grey box marks missing records.")
    all_batches = list_product_batches(graph)
    options = ["(none)"] + all_batches
    cmp_default = options.index("PB-040") if "PB-040" in options else 0
    cmp_id = st.selectbox("Compare with product batch", options, index=cmp_default, key="graph_cmp")
    cmp_result = explain_batch(graph, cmp_id, target["lot_ids"]) if cmp_id != "(none)" else None
    st.graphviz_chart(build_dot(result, cmp_result), use_container_width=True)
    legend_html = " ".join(
        pill(k) if k != "LOT" else '<span class="tb-pill tb-green"><i></i>Affected lot</span>'
        for k, _ in LEGEND)
    st.markdown(f'<div class="tb-row">{legend_html}</div>', unsafe_allow_html=True)

with tab_ship:
    st.dataframe([{
        "Shipment": x["shipment_id"], "Exposure": BADGE[x["exposure"]],
        "Destination": f"{x['location_id']} ({x['location_name']})",
        "Product batches": ", ".join(f"{b['product_batch_id']} ({b['quantity']})" for b in x["product_batches"]),
    } for x in a["shipments"]], use_container_width=True)
    for x in a["shipments"]:
        with st.expander(f"Evidence: {x['shipment_id']} - {BADGE[x['exposure']]}"):
            for e in x["evidence"]:
                st.code(e["path_text"], language=None)

with tab_gap:
    if not a["provenance_gaps"]:
        st.success("No provenance gaps found at the affected facilities.")
    for g in a["provenance_gaps"]:
        st.warning(f"**{g['production_batch_id']}** ({g['facility_id']}): {g['reason']}")
        st.write("Product batches made from it: " + (", ".join(g["product_batches"]) or "none recorded"))
    st.caption("Missing records are shown as uncertainty. They are never treated as safe.")

with tab_why:
    batches = list_product_batches(graph)
    default = batches.index("PB-040") if "PB-040" in batches else 0
    pick = st.selectbox("Product batch", batches, index=default)
    ex = explain_batch(graph, pick, target["lot_ids"])
    st.markdown(pill(ex["verdict"]), unsafe_allow_html=True)
    st.write(ex["explanation"])
    for p in ex["producers"]:
        st.write(f"Produced by **{p['production_batch_id']}** at {p['facility_id']}; "
                 f"recorded lots: {', '.join(p['lots']) or 'none'}")

with tab_act:
    if not incident:
        st.info("Link an incident to this lot to see and review actions.")
    else:
        actions = act.list_actions(graph, incident["incident_id"])
        for ac in actions:
            with st.container(border=True):
                st.markdown(f"**{ac['action_type'].replace('_', ' ').title()}** "
                            f"{chip(ac['target_type'] + ' ' + ac['target_id'])} "
                            f"{pill(ac['status'])} {pill(ac['exposure'])}", unsafe_allow_html=True)
                st.write(ac["rationale"])
                with st.expander("Supporting evidence"):
                    st.code(ac["evidence"], language=None)
                if ac["status"] == "PROPOSED":
                    b1, b2, _ = st.columns([1, 1, 6])
                    approve = b1.button("Approve", key=f"ap-{ac['action_id']}", disabled=not reviewer)
                    reject = b2.button("Reject", key=f"rj-{ac['action_id']}", disabled=not reviewer)
                    if approve or reject:
                        try:
                            act.record_action_decision(graph, ac["action_id"],
                                                       "APPROVED" if approve else "REJECTED", reviewer)
                            st.rerun()
                        except (ValueError, LookupError) as exc:
                            st.error(str(exc))
                    if not reviewer:
                        st.caption("Enter your name in the sidebar to enable review.")
                else:
                    st.caption(f"{ac['status']} by {ac['reviewer']} at {ac['reviewed_at']}")
