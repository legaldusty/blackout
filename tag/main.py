import bluetooth
from machine import Pin, Timer

CHIP_HZ = 15
CHIPS = {
    "hide_all": (0, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1),
    "hide_face": (1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1, 0, 0, 0),
}
POLICY_BYTE = {"hide_all": 1, "hide_face": 2}

EMITTER_PIN = 5
INDICATOR_PIN = 2
ACTIVE_PIN = 18
MODE_PIN = 19

ADVERTISE_INTERVAL_US = 100_000
BEACON_PREFIX = bytes((0xFF, 0xFF, 0x4E, 0x50, 0x01))

emitter = Pin(EMITTER_PIN, Pin.OUT, value=0)
indicator = Pin(INDICATOR_PIN, Pin.OUT, value=0)
active_switch = Pin(ACTIVE_PIN, Pin.IN, Pin.PULL_UP)
mode_switch = Pin(MODE_PIN, Pin.IN, Pin.PULL_UP)

radio = bluetooth.BLE()
state = {"index": 0, "policy": None}


def wanted_policy():
    if active_switch.value() == 0:
        return None
    return "hide_all" if mode_switch.value() == 1 else "hide_face"


def advertise(policy):
    if policy is None:
        radio.gap_advertise(None)
        return
    body = BEACON_PREFIX + bytes((POLICY_BYTE[policy],))
    payload = bytes((2, 0x01, 0x06, len(body) + 1, 0xFF)) + body
    radio.gap_advertise(ADVERTISE_INTERVAL_US, adv_data=payload, connectable=False)


def tick(_):
    policy = wanted_policy()
    if policy != state["policy"]:
        state["policy"] = policy
        state["index"] = 0
        advertise(policy)
    if policy is None:
        emitter.value(0)
        indicator.value(0)
        return
    chip = CHIPS[policy][state["index"]]
    emitter.value(chip)
    indicator.value(chip)
    state["index"] = (state["index"] + 1) % len(CHIPS[policy])


def start():
    radio.active(True)
    for mode in (3, 1):
        try:
            radio.config(addr_mode=mode)
            break
        except (ValueError, OSError):
            continue
    Timer(0).init(freq=CHIP_HZ, mode=Timer.PERIODIC, callback=tick)


start()
