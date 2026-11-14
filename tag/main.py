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
    "ESP32S3": {"emitters": (1, 2, 3, 4), "indicator": 21, "indicator_on": 0, "active": 5, "mode": 6},
    "ESP32": {"emitters": (25, 26, 27, 33), "indicator": 2, "indicator_on": 1, "active": 18, "mode": 19},
}


def board():
    machine_name = os.uname().machine.upper()
    for key in ("ESP32S3", "ESP32"):
        if key in machine_name:
            return BOARDS[key]
    return BOARDS["ESP32"]


wiring = board()
emitters = [Pin(number, Pin.OUT, value=0) for number in wiring["emitters"]]
indicator = Pin(wiring["indicator"], Pin.OUT, value=1 - wiring["indicator_on"])
active_switch = Pin(wiring["active"], Pin.IN, Pin.PULL_UP)
mode_switch = Pin(wiring["mode"], Pin.IN, Pin.PULL_UP)

radio = bluetooth.BLE()
state = {"index": 0, "wish": None, "code": 0, "picked": 0}


def pick_code():
    state["code"] = os.urandom(1)[0] % len(CODES)
    state["picked"] = time.time()
    for mode in (3, 1):
        try:
            radio.config(addr_mode=mode)
            return
        except (ValueError, OSError):
            continue


def wanted_wish():
    if active_switch.value() == 0:
        return None
    return HIDE_ALL if mode_switch.value() == 1 else HIDE_FACE


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
    indicator.value(wiring["indicator_on"] if on else 1 - wiring["indicator_on"])


def tick(_):
    wish = wanted_wish()
    due = time.time() - state["picked"] >= ROTATE_SECONDS and state["index"] == 0
    if wish != state["wish"] or (due and wish is not None):
        if due or state["wish"] is None:
            pick_code()
        state["wish"] = wish
        state["index"] = 0
        advertise(wish)
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
