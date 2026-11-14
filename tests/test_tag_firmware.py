import ast
from pathlib import Path

from eye.beacon import CHIP_RATE, CHIPS, Policy

SOURCE = Path(__file__).resolve().parents[1] / "tag" / "main.py"


def constants():
    found = {}
    for node in ast.parse(SOURCE.read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                found[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return found


def test_tag_blinks_the_same_codes_the_camera_reads():
    chips = constants()["CHIPS"]
    assert chips == {policy.value: CHIPS[policy] for policy in Policy}


def test_tag_blinks_at_the_rate_the_camera_expects():
    assert constants()["CHIP_HZ"] == CHIP_RATE
