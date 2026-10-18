import config


def get_graph(name=None):
    """Return a handle to the named graph (defaults to config.GRAPH_NAME)."""
    from falkordb import FalkorDB  # imported lazily so pure-logic modules/tests need no driver

    db = FalkorDB(host=config.FALKORDB_HOST, port=config.FALKORDB_PORT)
    return db.select_graph(name or config.GRAPH_NAME)
