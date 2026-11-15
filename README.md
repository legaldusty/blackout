# Blackout

Not pictured.

Blackout is a small tag that tells cameras "leave me out", and camera software that listens. The person wearing the tag is erased inside the camera, before any video is saved or sent. A second kind of tag does the same thing for a whole room.

It was built in one weekend for a hackathon prompt about data privacy guardrails, under UN Sustainable Development Goal 16.

## Why

Glasses with cameras and home robots film the people around them and send that video away. The people in the picture never agreed to it and have no way to say no. Blackout gives them a switch, and gives an honest camera a way to obey it.

## How it works

### The tag

The tag is an ESP32 board running MicroPython (`tag/main.py`). When it is on, it says the same thing in two ways.

- Radio. A Bluetooth advertisement carries the tag's wish (hide all of me, hide my face only, or hide this room) and the number of the blink code it is using right now.
- Light. An infrared LED blinks that code. People cannot see it. A code is 15 on or off steps sent at 15 steps a second, so it repeats once a second. There are 8 codes, shared by every tag.

The tag has no serial number and no account. It picks a new code at random every five minutes and uses a random Bluetooth address.

One button runs the badge. A short press turns it on or off. Holding it for about a second switches between hiding the whole body and hiding the face only. A small status light breathes while the tag is on.

### The camera

The camera unit is a Raspberry Pi 5 with two cameras (`eye/`).

- The scene camera films the room. This is the picture that would normally be recorded.
- The tag camera sits behind a dark window that blocks visible light. It sees almost nothing except blinking tags.

Every frame goes through these steps.

1. Listen. The Pi collects Bluetooth announcements from nearby tags.
2. Look. The tag camera tracks bright spots and reads the blink pattern of each one. It only accepts codes that a tag has announced over radio, so a flickering lamp cannot pass as a tag.
3. Match. The spot is mapped into the scene camera's picture, and the person whose body contains that point is the wearer.
4. Erase. The wearer is painted over as a solid black silhouette, or just their face if that is their wish. Solid, not blur, because blur can leak a shape.
5. Release. The video leaves the camera 2.5 seconds late. That delay lets the erase cover the moment before the code was read.

A local web page (`site/`) shows the only picture that leaves the camera, plus live counts: tags heard, people erased, frames a second.

### Safety rules

- Hold. If the camera hears a tag but cannot find its light, for example when the wearer has their back turned, it hides every person it has not matched until it finds the light. It hides too much, never too little.
- Sticky. Once a person is matched they stay erased while the camera tracks them, even if the tag gets covered.
- Fail closed. If the software hits an error, or the person detector falls more than 0.8 seconds behind, the output goes black. It never falls back to the raw video.
- Short count. If a frame would cover fewer people than there are tags asking, that frame is not shown.
- Room tags. A room tag sends radio only. Any camera that hears it hides every person in view. Nobody in the room has to wear anything.

## Hardware

- Raspberry Pi 5 with the active cooler
- Raspberry Pi Camera Module 3 NoIR Wide, behind the dark infrared window from a TV remote (the tag camera)
- USB webcam (the scene camera)
- ESP32 dev boards, one per tag
- An infrared LED from a TV remote, driven by four pins through four resistors, plus a visible status LED
- 3D printed cases for the camera unit and the badges (`case/`)

## Repo layout

| Folder | What is in it |
| --- | --- |
| `eye/` | Camera side: blink reader, spot tracker, person detector, pipeline, Bluetooth listener, web server, camera line-up tool |
| `tag/` | Tag firmware for the ESP32 |
| `tools/` | Script that flashes a tag, Pi setup script |
| `site/` | The page that shows what leaves the camera |
| `case/` | Blender scripts and STL files for the printed parts |
| `tests/` | Automated tests |

## Running it

Set up Python 3.12 or newer.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install numpy opencv-python mediapipe bleak pytest esptool mpremote
```

Run the tests. They cover the blink reader against noise, light flicker and dropped frames, the matching and safety rules, and the tag firmware logic.

```bash
.venv/bin/python -m pytest -q
```

Flash a badge tag. Plug the ESP32 in with a data cable first. A full flash needs the MicroPython image for your board saved in `firmware/`.

```bash
.venv/bin/python tools/flash.py
```

Flash a room tag instead.

```bash
.venv/bin/python tools/flash.py --room
```

Line up the two cameras. In a well lit room the tool matches the room itself between the two pictures and saves `align.npy`. Add `--upside-down` if the tag camera is mounted upside down, as it is in the printed housing.

```bash
python -m eye.lineup --still
```

Start the camera, then open port 8000 on the Pi in a browser.

```bash
python -m eye.app --webcam
```

The person detection models download into `models/` the first time the camera starts.

## What we measured

One walk test with the real badge and camera, indoors in daylight with the room lights on. The camera's state was read about 14 times a second while the wearer stood still for 10 seconds at each spot. The raw results are in `site/proof.json`.

| Test | Result |
| --- | --- |
| Badge matched at 1, 2 and 3 metres | 100% of checks |
| Badge matched at 4 metres | 96% |
| Badge matched at 5 metres | 43%, with the wearer still hidden in 96% of checks by the hold rule |
| Wearer hidden with their back turned at 2 metres | 100% |
| Exactly one person erased with two people side by side | 100% |
| Speed while erasing | 39 frames a second |
| Checks where the wearer was left uncovered | 7 of 832, all at 4 to 5 metres |

Those 7 uncovered checks are what led to the short count rule above. That rule was added after this walk and has not been measured on the hardware yet.

## Limits

- The tag camera needs a line of sight to the tag's light. When it has none, the hold rule hides everyone, which is safe but blunt.
- Range is short. See the numbers below.
- A camera has to run this software to honor a tag. A camera that ignores the signal is not stopped by it. Blackout is a standard that honest devices can follow and that rules can require, like a crosswalk signal.
- It hides who a person is, not what they do. The silhouette and its actions stay visible.
- The two cameras must be lined up again whenever one of them moves.
