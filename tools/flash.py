import argparse
import glob
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = {
    "ESP32-S3": (ROOT / "firmware" / "ESP32_GENERIC_S3.bin", "0x0"),
    "ESP32": (ROOT / "firmware" / "ESP32_GENERIC.bin", "0x1000"),
}
PORT_PATTERNS = ("/dev/cu.usbserial*", "/dev/cu.usbmodem*", "/dev/cu.wchusbserial*", "/dev/cu.SLAB*", "/dev/ttyUSB*", "/dev/ttyACM*")


def find_ports() -> list[str]:
    found: list[str] = []
    for pattern in PORT_PATTERNS:
        found.extend(sorted(glob.glob(pattern)))
    return found


def tool(*parts: str) -> str:
    done = subprocess.run([sys.executable, "-m", *parts], capture_output=True, text=True)
    if done.returncode != 0:
        print(done.stdout + done.stderr)
        raise SystemExit(f"{parts[0]} failed")
    return done.stdout


def chip_family(port: str) -> str:
    text = tool("esptool", "--port", port, "chip-id")
    return "ESP32-S3" if "ESP32-S3" in text else "ESP32"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    parser.add_argument("--code-only", action="store_true")
    args = parser.parse_args()
    ports = [args.port] if args.port else find_ports()
    if not ports:
        raise SystemExit("no board found, plug it in with a data cable")
    if len(ports) > 1:
        raise SystemExit("more than one board found, pick one with --port: " + ", ".join(ports))
    port = ports[0]
    if not args.code_only:
        family = chip_family(port)
        image, offset = FIRMWARE[family]
        print(f"{family} on {port}, erasing")
        tool("esptool", "--port", port, "erase-flash")
        print("writing MicroPython")
        tool("esptool", "--port", port, "--baud", "460800", "write-flash", offset, str(image))
        time.sleep(2.0)
    print("copying tag code")
    tool("mpremote", "connect", port, "cp", str(ROOT / "tag" / "main.py"), ":main.py")
    tool("mpremote", "connect", port, "reset")
    print("done, the tag is blinking if its switch is on")


if __name__ == "__main__":
    main()
