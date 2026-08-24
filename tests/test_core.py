from graphbench.core import NodeRow, choose_start_ids, percentiles
from graphbench.report import render_markdown


def test_percentiles_are_deterministic():
    result = percentiles([5, 1, 3, 2, 4])
    assert result["count"] == 5
    assert result["p50"] == 3
    assert result["p95"] == 5
    assert result["mean"] == 3


def test_choose_start_ids_is_repeatable():
    nodes = [NodeRow(i, f"u-{i}", "IN", 20) for i in range(20)]
    assert choose_start_ids(nodes, 10, 7) == choose_start_ids(nodes, 10, 7)


def test_markdown_report_contains_required_columns():
    markdown = render_markdown({"rows": [{
        "database": "test", "workload": "1-hop", "count": 2,
        "p50": 1.0, "p95": 2.0, "p99": 2.0, "mean": 1.5,
        "successful": 2, "failed": 0, "concurrency": None,
    }]})
    assert "p50 (ms)" in markdown
    assert "p95 (ms)" in markdown
    assert "| test | 1-hop |" in markdown
