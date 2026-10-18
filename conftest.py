"""Shared fixtures. DB tests use a separate 'traceback_test' graph (needs FalkorDB running);
pure tests (test_impact_assessment.py, test_action_workflow.py) need no database."""
import pytest


def _make_graph():
    from graph.connection import get_graph
    from graph.seed_data import seed
    g = get_graph("traceback_test")
    seed(g)
    return g


def _cleanup(g):
    try:
        g.delete()
    except Exception:
        pass


@pytest.fixture(scope="module")
def graph():
    g = _make_graph()
    yield g
    _cleanup(g)


@pytest.fixture()
def fresh_graph():
    g = _make_graph()
    yield g
    _cleanup(g)
