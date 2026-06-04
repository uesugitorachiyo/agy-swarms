from pathlib import Path

import pytest

from agy_swarms.graph_io import GraphLoadError, load_graph


def test_load_graph_parses_two_command_nodes(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        """
        {
          "nodes": [
            {"id": "a", "role": "test", "objective": "echo a", "command": ["python", "-c", "print('a')"]},
            {"id": "b", "role": "verify", "objective": "echo b", "dependencies": ["a"], "command": ["python", "-c", "print('b')"]}
          ],
          "edges": [["a", "b"]]
        }
        """,
        encoding="utf-8",
    )

    graph = load_graph(graph_file)

    assert [node.id for node in graph.nodes] == ["a", "b"]
    assert graph.edges == (("a", "b"),)
    assert graph.nodes[0].command == ["python", "-c", "print('a')"]


def test_load_graph_materializes_edges_into_dependencies(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        """
        {
          "nodes": [
            {"id": "a", "role": "test", "objective": "echo a"},
            {"id": "b", "role": "verify", "objective": "echo b"}
          ],
          "edges": [["a", "b"]]
        }
        """,
        encoding="utf-8",
    )

    graph = load_graph(graph_file)

    assert graph.edges == (("a", "b"),)
    assert graph.nodes[1].dependencies == ["a"]


def test_load_graph_rejects_missing_nodes(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text('{"edges": []}', encoding="utf-8")

    with pytest.raises(GraphLoadError, match="nodes"):
        load_graph(graph_file)


def test_load_graph_rejects_edge_with_unknown_endpoint(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        """
        {
          "nodes": [{"id": "a", "role": "test", "objective": "echo a"}],
          "edges": [["a", "missing"]]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(GraphLoadError, match="unknown edge endpoint"):
        load_graph(graph_file)


def test_load_graph_rejects_string_command_before_dispatch(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        """
        {
          "nodes": [{"id": "a", "role": "test", "objective": "echo a", "command": "python -c pass"}],
          "edges": []
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(
        GraphLoadError,
        match="command for node 'a' must be a non-empty array of strings",
    ):
        load_graph(graph_file)


def test_load_graph_rejects_non_string_command_argument(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        """
        {
          "nodes": [{"id": "a", "role": "test", "objective": "echo a", "command": ["python", 3]}],
          "edges": []
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(
        GraphLoadError,
        match="command for node 'a' must be a non-empty array of strings",
    ):
        load_graph(graph_file)


def test_load_graph_rejects_empty_command_array(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        """
        {
          "nodes": [{"id": "a", "role": "test", "objective": "echo a", "command": []}],
          "edges": []
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(
        GraphLoadError,
        match="command for node 'a' must be a non-empty array of strings",
    ):
        load_graph(graph_file)


def test_load_graph_redacts_sensitive_unknown_edge_endpoint(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        """
        {
          "nodes": [{"id": "safe", "role": "test", "objective": "echo safe"}],
          "edges": [["safe", "GEMINI_API_KEY=secret-token-value"]]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(GraphLoadError) as exc_info:
        load_graph(graph_file)

    message = str(exc_info.value)
    assert "unknown edge endpoint at edge[0]" in message
    assert "target=<redacted>" in message
    assert "GEMINI_API_KEY" not in message
    assert "secret-token-value" not in message


def test_load_graph_redacts_sensitive_node_id_in_command_error(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        """
        {
          "nodes": [
            {
              "id": "/Users/operator/.config/agy/oauth-token",
              "role": "test",
              "objective": "echo",
              "command": "python -c pass"
            }
          ],
          "edges": []
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(GraphLoadError) as exc_info:
        load_graph(graph_file)

    message = str(exc_info.value)
    assert "command for node[0] <redacted>" in message
    assert "/Users/operator" not in message
    assert "oauth-token" not in message


def test_load_graph_read_error_does_not_expose_absolute_path(tmp_path: Path):
    graph_file = tmp_path / "secret-project" / "missing.json"

    with pytest.raises(GraphLoadError) as exc_info:
        load_graph(graph_file)

    message = str(exc_info.value)
    assert "cannot read graph file" in message
    assert str(tmp_path) not in message
    assert "missing.json" in message
