"""Version-bound coupon size; historical policies remain triples."""
DOUBLE_POLICY = "LAB_COMBO_DOUBLE_170_P70_80_20261006_V1"


def leg_count(value: dict) -> int:
    """Only the explicitly versioned Double contract accepts two selections."""
    return 2 if value.get("combo_selection_policy") == DOUBLE_POLICY and value.get("policy") == DOUBLE_POLICY else 3
