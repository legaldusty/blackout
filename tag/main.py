import os
import time

import bluetooth
from machine import PWM, Pin, Timer

CHIP_HZ = 15
CODES = (
    (0, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1),
    (0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 1),
    (0, 0, 0, 0, 1, 1, 1, 0, 1, 1, 0, 0, 1, 0, 1),
    (0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1),
    (0, 0, 0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 1, 0, 1),
    (0, 0, 0, 0, 1, 0, 1, 0, 1, 0, 0, 1, 1, 1, 1),
    (0, 0, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1),
    (0, 0, 0, 1, 0, 1, 1, 1, 1, 0, 1, 0, 0, 1, 1),
)
HIDE_ALL = 1
HIDE_FACE = 2
ROOM = 3

COMPANY_ID = 0xFFFF
BEACON_PREFIX = bytes((0x4E, 0x50, 0x02))
ADVERTISE_INTERVAL_US = 100_000
ROTATE_SECONDS = 300

BOARDS = {
    "ESP32S3": {"emitters": (1, 2, 3, 4), "status": 5, "onboard": 21, "button": 0},
    "ESP32": {"emitters": (25, 26, 27, 33), "status": 19, "onboard": 2, "button": 0},
}
HOLD_TICKS = 18
BREATH_TICKS = 45
BREATH_LOW = 6000
BREATH_HIGH = 65535
LINEUP_TICKS = CHIP_HZ * 120


def board():
    machine_name = os.uname().machine.upper()
    for key in ("ESP32S3", "ESP32"):
        if key in machine_name:
            return BOARDS[key]
    return BOARDS["ESP32"]


wiring = board()
emitters = [Pin(number, Pin.OUT, value=0) for number in wiring["emitters"]]
status = PWM(Pin(wiring["status"]), freq=1000, duty_u16=0)
onboard = Pin(wiring["onboard"], Pin.OUT, value=0)
is_room = "room" in os.listdir()
button = Pin(wiring["button"], Pin.IN, Pin.PULL_UP)

radio = bluetooth.BLE()
state = {"index": 0, "wish": None, "code": 0, "picked": 0, "active": True, "face_only": False, "held": 0, "flash": 0, "breath": 0, "age": 0}


def pick_code():
    state["code"] = os.urandom(1)[0] % len(CODES)
    state["picked"] = time.time()
    for mode in (3, 1):
        try:
            radio.config(addr_mode=mode)
            return
        except (ValueError, OSError):
            continue


def read_button():
    if button.value() == 0:
        state["held"] += 1
        if state["held"] == HOLD_TICKS and not is_room:
            state["face_only"] = not state["face_only"]
            state["active"] = True
            state["flash"] = 12
        return
    if 0 < state["held"] < HOLD_TICKS:
        state["active"] = not state["active"]
    state["held"] = 0


def wanted_wish():
    if not state["active"]:
        return None
    if is_room:
        return ROOM
    return HIDE_FACE if state["face_only"] else HIDE_ALL


def advertise(wish):
    if wish is None:
        radio.gap_advertise(None)
        return
    body = bytes((COMPANY_ID & 0xFF, COMPANY_ID >> 8)) + BEACON_PREFIX + bytes((wish, state["code"]))
    payload = bytes((2, 0x01, 0x06, len(body) + 1, 0xFF)) + body
    radio.gap_advertise(ADVERTISE_INTERVAL_US, adv_data=payload, connectable=False)


def shine(on):
    for pin in emitters:
        pin.value(0 if is_room else on)


def show_status(wish, chip):
    onboard.value(0 if wish is None else 1)
    if state["age"] < LINEUP_TICKS:
        state["age"] += 1
        if wish is not None and not is_room:
            status.duty_u16(BREATH_HIGH if chip else 0)
            return
    if state["flash"] > 0:
        state["flash"] -= 1
        status.duty_u16(BREATH_HIGH if (state["flash"] // 3) % 2 else 0)
        return
    if wish is None:
        status.duty_u16(0)
        return
    state["breath"] = (state["breath"] + 1) % BREATH_TICKS
    half = BREATH_TICKS // 2
    step = state["breath"] if state["breath"] <= half else BREATH_TICKS - state["breath"]
    status.duty_u16(BREATH_LOW + (BREATH_HIGH - BREATH_LOW) * step // half)


def tick(_):
    read_button()
    wish = wanted_wish()
    due = time.time() - state["picked"] >= ROTATE_SECONDS and state["index"] == 0
    if wish != state["wish"] or (due and wish is not None):
        if due or state["wish"] is None:
            pick_code()
        state["wish"] = wish
        state["index"] = 0
        advertise(wish)
    chip = 0 if wish is None else CODES[state["code"]][state["index"]]
    show_status(wish, chip)
    if wish is None:
        shine(0)
        return
    shine(chip)
    state["index"] = (state["index"] + 1) % len(CODES[state["code"]])


def start():
    radio.active(True)
    pick_code()
    Timer(0).init(freq=CHIP_HZ, mode=Timer.PERIODIC, callback=tick)


start()
