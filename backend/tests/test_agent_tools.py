"""
Unit tests for app.agent.tools — the safe-arithmetic sandbox (_safe_eval /
execute_calculate) and execute_retrieve_docs formatting.

The calculator tests include actual injection attempts, not just "does the
happy path work" — this function's whole reason to exist is to reject
exactly these inputs, so each rejection path needs its own assertion.
"""
from unittest.mock import MagicMock, patch

from app.agent.tools import execute_calculate, execute_retrieve_docs


# ---- calculate: happy path -------------------------------------------------


def test_calculate_basic_arithmetic():
    assert execute_calculate("2 + 2") == "4"


def test_calculate_order_of_operations():
    assert execute_calculate("2 + 3 * 4") == "14"


def test_calculate_applies_ratio_to_bodyweight():
    # the actual real-world shape of calls this tool will get: applying a
    # retrieved g/kg guideline to a user's weight
    assert execute_calculate("80 * 1.6") == "128.0"


def test_calculate_division_by_zero():
    assert execute_calculate("1 / 0") == "Error: division by zero"


# ---- calculate: injection attempts -----------------------------------------


def test_calculate_rejects_dunder_import():
    result = execute_calculate("__import__('os').system('echo pwned')")
    assert result.startswith("Error evaluating expression:")


def test_calculate_rejects_open_call():
    result = execute_calculate("open('/etc/passwd').read()")
    assert result.startswith("Error evaluating expression:")


def test_calculate_rejects_list_comprehension():
    result = execute_calculate("[x for x in range(10)]")
    assert result.startswith("Error evaluating expression:")


def test_calculate_rejects_bare_name():
    result = execute_calculate("os")
    assert result.startswith("Error evaluating expression:")


def test_calculate_rejects_string_literal():
    result = execute_calculate("'2 + 2'")
    assert result.startswith("Error evaluating expression:")


def test_calculate_rejects_boolean():
    # Python's bool is a subclass of int — explicitly excluded in _safe_eval
    # so True/False can't smuggle through as 1/0
    result = execute_calculate("True + 1")
    assert result.startswith("Error evaluating expression:")


def test_calculate_malformed_expression():
    result = execute_calculate("2 +")
    assert result.startswith("Error evaluating expression:")


# ---- execute_retrieve_docs --------------------------------------------------


def test_execute_retrieve_docs_formats_results():
    fake_db = MagicMock()
    fake_client = MagicMock()

    with patch("app.agent.tools.get_query_embedding", return_value=[0.1] * 1024), patch(
        "app.agent.tools.search_chunks",
        return_value=[
            {
                "content": "Adults need 1.2 to 1.6 grams of protein per kg of body weight.",
                "section": "Protein",
                "title": "Dietary Guidelines for Americans 2025-2030",
                "citation_url": "https://www.dietaryguidelines.gov",
                "distance": 0.12,
            }
        ],
    ):
        result = execute_retrieve_docs(fake_db, fake_client, "protein intake")

    assert "Dietary Guidelines for Americans 2025-2030" in result
    assert "Protein" in result
    assert "1.2 to 1.6 grams" in result
    assert "https://www.dietaryguidelines.gov" in result


def test_execute_retrieve_docs_empty_corpus():
    fake_db = MagicMock()
    fake_client = MagicMock()

    with patch("app.agent.tools.get_query_embedding", return_value=[0.1] * 1024), patch(
        "app.agent.tools.search_chunks", return_value=[]
    ):
        result = execute_retrieve_docs(fake_db, fake_client, "something not in the corpus")

    assert result == "No relevant documents found in the knowledge base."
