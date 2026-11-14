import ast
from pathlib import Path

from eye import radio
from eye.beacon import CHIP_RATE, CODES, Policy

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
    assert constants()["CODES"] == CODES


def test_tag_blinks_at_the_rate_the_camera_expects():
    assert constants()["CHIP_HZ"] == CHIP_RATE


def test_tag_and_camera_agree_on_the_wish_numbers():
    found = constants()
    assert found["HIDE_ALL"] == Policy.HIDE_ALL.value
    assert found["HIDE_FACE"] == Policy.HIDE_FACE.value


def test_camera_understands_what_the_tag_broadcasts():
    found = constants()
    assert found["COMPANY_ID"] == radio.COMPANY_ID
    source = SOURCE.read_text()
    assert "bytes((0x4E, 0x50, 0x02))" in source
    assert radio.BEACON_PREFIX == bytes((0x4E, 0x50, 0x02))
    body = radio.BEACON_PREFIX + bytes((found["HIDE_FACE"], 6))
    heard = radio.parse_payload("aa", body)
    assert heard is not None and heard.code == 6 and heard.policy is Policy.HIDE_FACE


def test_camera_ignores_other_bluetooth_devices():
    assert radio.parse_payload("aa", b"\x01\x02\x03\x04\x05") is None
    assert radio.parse_payload("aa", radio.BEACON_PREFIX + bytes((1, 99))) is None
    assert radio.parse_payload("aa", radio.BEACON_PREFIX + bytes((9, 1))) is None
