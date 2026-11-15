import os
import time

import bluetooth
from machine import Pin, Timer

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

COMPANY_ID = 0xFFFF
BEACON_PREFIX = bytes((0x4E, 0x50, 0x02))
ADVERTISE_INTERVAL_US = 100_000
ROTATE_SECONDS = 300

BOARDS = {
    "ESP32S3": {"emitters": (1, 2, 3, 4), "status": 5, "button": 0},
    "ESP32": {"emitters": (25, 26, 27, 33), "status": 19, "button": 0},
}
HOLD_TICKS = 18


def board():
    machine_name = os.uname().machine.upper()
    for key in ("ESP32S3", "ESP32"):
        if key in machine_name:
            return BOARDS[key]
    return BOARDS["ESP32"]


wiring = board()
emitters = [Pin(number, Pin.OUT, value=0) for number in wiring["emitters"]]
status = Pin(wiring["status"], Pin.OUT, value=0)
button = Pin(wiring["button"], Pin.IN, Pin.PULL_UP)

radio = bluetooth.BLE()
state = {"index": 0, "wish": None, "code": 0, "picked": 0, "active": True, "face_only": False, "held": 0, "flash": 0}


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
        if state["held"] == HOLD_TICKS:
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
        pin.value(on)


def show_status(wish):
    if state["flash"] > 0:
        state["flash"] -= 1
        status.value((state["flash"] // 3) % 2)
        return
    status.value(0 if wish is None else 1)


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
    show_status(wish)
    if wish is None:
        shine(0)
        return
    shine(CODES[state["code"]][state["index"]])
    state["index"] = (state["index"] + 1) % len(CODES[state["code"]])


def start():
    radio.active(True)
    pick_code()
    Timer(0).init(freq=CHIP_HZ, mode=Timer.PERIODIC, callback=tick)


start()
