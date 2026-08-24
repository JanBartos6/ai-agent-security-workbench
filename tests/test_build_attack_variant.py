from scripts.build_attack_variant import _apply_sets, _constant_values


def test_apply_sets_replaces_multiline_parenthesized_constant() -> None:
    source = """\
FOO = (
    "a,"
    "b"
)
BAR = True
"""

    updated = _apply_sets(source, {"FOO": '"x,y"'})
    values = _constant_values(updated)

    assert '    "a,"' not in updated
    assert values["FOO"] == "x,y"
    assert values["BAR"] is True

