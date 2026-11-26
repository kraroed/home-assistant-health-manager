"""Regression coverage for initially empty Home Assistant text helpers."""
import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
TEXT_SOURCE = ROOT / "custom_components" / "home_assistant_health_manager" / "text.py"


def _class_node(tree, name):
    return next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _method(class_node, name):
    return next(
        node for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _native_value_returns(class_node):
    method = _method(class_node, "native_value")
    return [
        node.value for node in ast.walk(method)
        if isinstance(node, ast.Return)
    ]


def _ends_in_none(expression):
    return (
        isinstance(expression, ast.BoolOp)
        and isinstance(expression.op, ast.Or)
        and isinstance(expression.values[-1], ast.Constant)
        and expression.values[-1].value is None
    )


def test_nonempty_minimum_text_helpers_return_none_until_selected():
    tree = ast.parse(TEXT_SOURCE.read_text(encoding="utf-8"))
    expected = {
        "EntityClassificationReasonText": 1,
        "EntityClassificationTargetText": 3,
        "UnavailableInvestigationEntityText": 3,
    }

    for class_name, minimum in expected.items():
        node = _class_node(tree, class_name)
        minimum_value = next(
            item.value for item in node.body
            if isinstance(item, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "_attr_native_min"
                for target in item.targets
            )
        )
        assert isinstance(minimum_value, ast.Constant)
        assert minimum_value.value == minimum
        assert any(_ends_in_none(value) for value in _native_value_returns(node)), (
            f"{class_name} must expose an unset value as None, not an invalid empty string"
        )


def test_unavailable_investigation_note_still_allows_an_empty_value():
    tree = ast.parse(TEXT_SOURCE.read_text(encoding="utf-8"))
    node = _class_node(tree, "UnavailableInvestigationNoteText")
    minimum_value = next(
        item.value for item in node.body
        if isinstance(item, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "_attr_native_min"
            for target in item.targets
        )
    )
    assert minimum_value.value == 0
    returns = _native_value_returns(node)
    assert len(returns) == 1
    assert not _ends_in_none(returns[0])
