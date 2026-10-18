"""Loads SYNTHETIC demo data into FalkorDB. Not real supply-chain data."""
from graph.connection import get_graph

SEED_CYPHER = """
CREATE
  (s17:Supplier {supplier_id:'S-17', name:'Halden Ingredients (synthetic)', status:'ACTIVE'}),
  (s22:Supplier {supplier_id:'S-22', name:'Brightmoor Foods (synthetic)', status:'ACTIVE'}),

  (l204:ComponentLot {lot_id:'L-204', component_name:'Sweetener syrup', status:'SUSPECT',  provenance_status:'COMPLETE'}),
  (l205:ComponentLot {lot_id:'L-205', component_name:'Sweetener syrup', status:'RELEASED', provenance_status:'COMPLETE'}),
  (l310:ComponentLot {lot_id:'L-310', component_name:'Oat binder',      status:'RELEASED', provenance_status:'COMPLETE'}),

  (inc:Incident {incident_id:'INC-001', incident_type:'CONTAMINATION',
     description:'Supplier S-17 reports contamination in lot L-204 (synthetic demo incident)',
     severity:'HIGH', status:'OPEN', reported_at:'2026-10-10T09:00:00Z'}),

  (pr12:ProductionBatch {production_batch_id:'PR-012', facility_id:'FAC-A', produced_at:'2026-10-01', components_recorded:true}),
  (pr13:ProductionBatch {production_batch_id:'PR-013', facility_id:'FAC-A', produced_at:'2026-10-02', components_recorded:true}),
  (pr14:ProductionBatch {production_batch_id:'PR-014', facility_id:'FAC-B', produced_at:'2026-10-02', components_recorded:true}),
  (pr15:ProductionBatch {production_batch_id:'PR-015', facility_id:'FAC-A', produced_at:'2026-10-03', components_recorded:true}),
  (pr16:ProductionBatch {production_batch_id:'PR-016', facility_id:'FAC-A', produced_at:'2026-10-04', components_recorded:false}),

  (pb31:ProductBatch {product_batch_id:'PB-031', product_name:'Protein bar', provenance_status:'COMPLETE'}),
  (pb32:ProductBatch {product_batch_id:'PB-032', product_name:'Protein bar', provenance_status:'COMPLETE'}),
  (pb33:ProductBatch {product_batch_id:'PB-033', product_name:'Protein bar', provenance_status:'COMPLETE'}),
  (pb34:ProductBatch {product_batch_id:'PB-034', product_name:'Protein bar', provenance_status:'COMPLETE'}),
  (pb40:ProductBatch {product_batch_id:'PB-040', product_name:'Protein bar', provenance_status:'COMPLETE'}),
  (pb50:ProductBatch {product_batch_id:'PB-050', product_name:'Protein bar', provenance_status:'INCOMPLETE'}),

  (sh14:Shipment {shipment_id:'SH-014', dispatch_date:'2026-10-05', status:'DISPATCHED'}),
  (sh15:Shipment {shipment_id:'SH-015', dispatch_date:'2026-10-06', status:'DISPATCHED'}),
  (sh16:Shipment {shipment_id:'SH-016', dispatch_date:'2026-10-06', status:'DISPATCHED'}),
  (sh17:Shipment {shipment_id:'SH-017', dispatch_date:'2026-10-07', status:'DISPATCHED'}),
  (sh18:Shipment {shipment_id:'SH-018', dispatch_date:'2026-10-07', status:'DISPATCHED'}),
  (sh19:Shipment {shipment_id:'SH-019', dispatch_date:'2026-10-08', status:'DISPATCHED'}),

  (wh03:Location {location_id:'WH-03', name:'North DC', location_type:'WAREHOUSE', region:'North'}),
  (wh04:Location {location_id:'WH-04', name:'East DC',  location_type:'WAREHOUSE', region:'East'}),
  (wh05:Location {location_id:'WH-05', name:'South DC', location_type:'WAREHOUSE', region:'South'}),
  (rt11:Location {location_id:'RT-11', name:'Retailer 11', location_type:'RETAILER', region:'North'}),
  (rt12:Location {location_id:'RT-12', name:'Retailer 12', location_type:'RETAILER', region:'East'}),

  (s17)-[:SUPPLIED]->(l204), (s17)-[:SUPPLIED]->(l205), (s22)-[:SUPPLIED]->(l310),
  (inc)-[:AFFECTS]->(l204),

  (l204)-[:USED_IN {verified:true,  source:'ERP batch record'}]->(pr12),
  (l204)-[:USED_IN {verified:true,  source:'ERP batch record'}]->(pr13),
  (l310)-[:USED_IN {verified:true,  source:'ERP batch record'}]->(pr13),
  (l205)-[:USED_IN {verified:true,  source:'ERP batch record'}]->(pr14),
  (l204)-[:USED_IN {verified:false, source:'handwritten line log'}]->(pr15),

  (pr12)-[:PRODUCED]->(pb31),
  (pr13)-[:PRODUCED]->(pb32), (pr13)-[:PRODUCED]->(pb33),
  (pr14)-[:PRODUCED]->(pb40),
  (pr15)-[:PRODUCED]->(pb34),
  (pr16)-[:PRODUCED]->(pb50),

  (pb31)-[:INCLUDED_IN {quantity:1000}]->(sh14),
  (pb32)-[:INCLUDED_IN {quantity:500}]->(sh15),
  (pb33)-[:INCLUDED_IN {quantity:300}]->(sh15),
  (pb33)-[:INCLUDED_IN {quantity:500}]->(sh16),
  (pb34)-[:INCLUDED_IN {quantity:600}]->(sh17),
  (pb40)-[:INCLUDED_IN {quantity:900}]->(sh18),
  (pb50)-[:INCLUDED_IN {quantity:400}]->(sh19),

  (sh14)-[:DELIVERED_TO]->(wh03), (sh15)-[:DELIVERED_TO]->(rt11), (sh16)-[:DELIVERED_TO]->(rt12),
  (sh17)-[:DELIVERED_TO]->(wh04), (sh18)-[:DELIVERED_TO]->(wh05), (sh19)-[:DELIVERED_TO]->(wh04)
"""

EXPECTED_NODES = 28
EXPECTED_RELS = 28


def seed(graph=None):
    """Reset the graph and load the demo data. Returns (node_count, rel_count)."""
    graph = graph or get_graph()
    try:
        graph.delete()  # fresh, deterministic start
    except Exception:
        pass  # graph did not exist yet
    graph.query(SEED_CYPHER)
    nodes = graph.ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
    rels = graph.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    assert (nodes, rels) == (EXPECTED_NODES, EXPECTED_RELS), f"got {nodes} nodes, {rels} rels"
    return nodes, rels


if __name__ == "__main__":
    n, r = seed()
    print(f"Seeded synthetic demo graph: {n} nodes, {r} relationships")
