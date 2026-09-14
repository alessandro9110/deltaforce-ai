import json

from deltaforce import databricks_io


def test_catalog_labels_are_sorted_and_long_comments_truncated():
    raw = json.dumps(
        [
            {"name": "workspace"},
            {"name": "samples", "comment": "These sample datasets are made available by third party providers " * 5},
            {"name": "main", "comment": "Main | catalog\nfor dev"},
        ]
    )
    items = databricks_io.parse_listing("catalogs", raw)
    assert [value for value, _ in items] == ["main", "samples", "workspace"]
    assert items[0][1] == "main — Main / catalog for dev"
    samples_label = items[1][1]
    assert samples_label.endswith("…")
    assert len(samples_label) <= len("samples — ") + databricks_io.COMMENT_MAX


def test_warehouses_nested_under_wrapper_key():
    raw = json.dumps({"warehouses": [{"id": "abc123", "name": "Starter", "state": "STOPPED"}]})
    assert databricks_io.parse_listing("warehouses", raw) == [("abc123", "Starter (abc123, STOPPED)")]


def test_single_user_object_and_empty_output():
    assert databricks_io.parse_listing("user", json.dumps({"userName": "me@example.com"})) == [
        ("me@example.com", "me@example.com")
    ]
    assert databricks_io.parse_listing("catalogs", "") == []
