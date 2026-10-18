"""All Cypher used by TraceBack lives here. Every query is parameterised; labels used in
dynamic queries come only from the TARGET_ID_PROPS whitelist."""

# ---- Resolve the starting entity -------------------------------------------------------
GET_LOT_CONTEXT = """
MATCH (l:ComponentLot {lot_id: $lot_id})
OPTIONAL MATCH (s:Supplier)-[:SUPPLIED]->(l)
OPTIONAL MATCH (i:Incident)-[:AFFECTS]->(l)
RETURN l.lot_id AS lot_id, l.component_name AS component_name, l.status AS lot_status,
       s.supplier_id AS supplier_id, s.name AS supplier_name,
       i.incident_id AS incident_id, i.severity AS severity,
       i.status AS incident_status, i.description AS description
ORDER BY incident_id
"""

GET_INCIDENT_LOTS = """
MATCH (i:Incident {incident_id: $incident_id})-[:AFFECTS]->(l:ComponentLot)
RETURN i.incident_id AS incident_id, i.severity AS severity, i.status AS incident_status,
       i.description AS description, l.lot_id AS lot_id
ORDER BY lot_id
"""

# ---- Query 1: lot -> production batch -> product batch (2 hops) ------------------------
# OPTIONAL MATCH keeps the lot row even when nothing is downstream, so
# "lot not found" (zero rows) differs from "lot found, no downstream" (one row of nulls).
TRACE_AFFECTED_BATCHES = """
MATCH (l:ComponentLot {lot_id: $lot_id})
OPTIONAL MATCH (l)-[u:USED_IN]->(pr:ProductionBatch)-[:PRODUCED]->(pb:ProductBatch)
RETURN l.lot_id AS lot_id,
       pr.production_batch_id AS production_batch_id,
       pb.product_batch_id AS product_batch_id,
       u.verified AS verified,
       u.source AS source
ORDER BY production_batch_id, product_batch_id
"""

# ---- Query 2/3: full 4-hop trace WITH evidence ----------------------------------------
# One row == one complete path lot -> production -> product -> shipment -> location.
# rel_types is read from the matched path itself so the app can verify the shape of the
# evidence FalkorDB actually returned.
DOWNSTREAM_PATHS = """
MATCH p = (l:ComponentLot)-[u:USED_IN]->(pr:ProductionBatch)-[:PRODUCED]->(pb:ProductBatch)
          -[inc:INCLUDED_IN]->(s:Shipment)-[:DELIVERED_TO]->(loc:Location)
WHERE l.lot_id IN $lot_ids
RETURN l.lot_id AS lot_id,
       pr.production_batch_id AS production_batch_id,
       pb.product_batch_id AS product_batch_id,
       s.shipment_id AS shipment_id,
       loc.location_id AS location_id,
       loc.name AS location_name,
       u.verified AS verified,
       u.source AS source,
       inc.quantity AS quantity,
       [r IN relationships(p) | type(r)] AS rel_types
ORDER BY shipment_id, product_batch_id, lot_id
"""

# ---- Query 4: provenance gaps ---------------------------------------------------------
# Production batches made at the same facility as an affected production batch that have
# NO recorded component consumption (no incoming USED_IN). The graph cannot link them to
# the incident and cannot clear them either.
PROVENANCE_GAPS = """
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
RETURN pr.production_batch_id AS production_batch_id,
       pr.facility_id AS facility_id,
       pb.product_batch_id AS product_batch_id,
       s.shipment_id AS shipment_id,
       loc.location_id AS location_id,
       loc.name AS location_name,
       inc.quantity AS quantity
ORDER BY production_batch_id, product_batch_id, shipment_id
"""

# ---- "Why is / isn't this batch affected?" ---------------------------------------------
UPSTREAM_OF_BATCH = """
MATCH (pb:ProductBatch {product_batch_id: $product_batch_id})
OPTIONAL MATCH (pr:ProductionBatch)-[:PRODUCED]->(pb)
OPTIONAL MATCH (l:ComponentLot)-[u:USED_IN]->(pr)
RETURN pb.product_batch_id AS product_batch_id,
       pr.production_batch_id AS production_batch_id,
       pr.facility_id AS facility_id,
       l.lot_id AS lot_id,
       u.verified AS verified,
       u.source AS source
ORDER BY production_batch_id, lot_id
"""

LIST_PRODUCT_BATCHES = """
MATCH (pb:ProductBatch)
RETURN pb.product_batch_id AS product_batch_id
ORDER BY product_batch_id
"""

# ---- Actions (audit trail) -------------------------------------------------------------
TARGET_ID_PROPS = {
    "Shipment": "shipment_id",
    "ProductBatch": "product_batch_id",
    "Location": "location_id",
    "ProductionBatch": "production_batch_id",
}


def target_exists_query(label):
    prop = TARGET_ID_PROPS[label]  # KeyError for anything not whitelisted
    return f"MATCH (t:{label} {{{prop}: $target_id}}) RETURN count(t)"


def link_target_query(label):
    prop = TARGET_ID_PROPS[label]
    return (
        f"MATCH (a:ContainmentAction {{action_id: $action_id}}) "
        f"MATCH (t:{label} {{{prop}: $target_id}}) "
        f"MERGE (a)-[:TARGETS]->(t) RETURN count(t)"
    )


CHECK_INCIDENT = "MATCH (i:Incident {incident_id: $incident_id}) RETURN count(i)"

# Idempotent: re-investigating never overwrites an action that was already created/decided.
UPSERT_PROPOSED_ACTION = """
MATCH (i:Incident {incident_id: $incident_id})
MERGE (a:ContainmentAction {action_id: $action_id})
ON CREATE SET a.status = 'PROPOSED', a.action_type = $action_type, a.exposure = $exposure,
              a.target_type = $target_type, a.target_id = $target_id,
              a.rationale = $rationale, a.evidence = $evidence,
              a.created_at = $now, a.simulated = true
MERGE (i)-[:TRIGGERED]->(a)
RETURN a.status AS status
"""

GET_ACTION_STATUS = """
MATCH (a:ContainmentAction {action_id: $action_id})
RETURN a.status AS status
"""

DECIDE_ACTION = """
MATCH (a:ContainmentAction {action_id: $action_id})
SET a.status = $status, a.reviewed_at = $now, a.reviewer = $reviewer, a.review_note = $note
RETURN a.status AS status
"""

LIST_ACTIONS = """
MATCH (i:Incident {incident_id: $incident_id})-[:TRIGGERED]->(a:ContainmentAction)
RETURN a.action_id AS action_id, a.action_type AS action_type, a.status AS status,
       a.exposure AS exposure, a.target_type AS target_type, a.target_id AS target_id,
       a.rationale AS rationale, a.evidence AS evidence, a.created_at AS created_at,
       a.reviewed_at AS reviewed_at, a.reviewer AS reviewer, a.review_note AS review_note
ORDER BY action_id
"""
