import argparse
import json
import subprocess
import time
import urllib.request
from datetime import date
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]


def speak(words: str, quiet: bool) -> None:
    print(words, flush=True)
    if not quiet:
        subprocess.run(["say", "-r", "170", words], check=False)


def read_state(host: str) -> dict | None:
    try:
        with urllib.request.urlopen(host + "/state.json", timeout=1.5) as reply:
            return json.loads(reply.read())
    except (OSError, ValueError):
        return None


def sample(host: str, seconds: float, rate: float = 15.0) -> list[dict]:
    found = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        began = time.monotonic()
        state = read_state(host)
        if state is not None:
            found.append(state)
        time.sleep(max(0.0, 1.0 / rate - (time.monotonic() - began)))
    return found


def hidden(state: dict) -> bool:
    return bool(state["tripped"] or state["holding"] or state["erased"] >= 1)


def matched(state: dict) -> bool:
    return bool(state["erased"] == 1 and not state["holding"] and not state["tripped"])


def share(samples: list[dict], test) -> float:
    return sum(1 for s in samples if test(s)) / len(samples) if samples else 0.0


def percent(value: float) -> str:
    return f"{round(value * 100)}%"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://blackout.local:8000")
    parser.add_argument("--distances", type=float, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--settle", type=float, default=8.0)
    parser.add_argument("--hold", type=float, default=10.0)
    parser.add_argument("--place", default="indoors, room lights on")
    parser.add_argument("--tests", type=int, default=0)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--out", default=str(HOME / "site" / "proof.json"))
    parser.add_argument("--raw", default=str(HOME / "recordings" / "proof_run.json"))
    args = parser.parse_args()

    if read_state(args.host) is None:
        raise SystemExit("the camera is not answering at " + args.host)

    stages = {}
    speak("Proof walk. One person wears the badge, switched on, facing the camera.", args.quiet)
    for distance in args.distances:
        speak(f"Stand at {distance:g} metres.", args.quiet)
        time.sleep(args.settle)
        stages[f"at_{distance:g}"] = sample(args.host, args.hold)
        speak("Done.", args.quiet)

    speak("Go to 2 metres and turn your back to the camera.", args.quiet)
    time.sleep(args.settle)
    stages["back"] = sample(args.host, args.hold)

    speak("Face the camera again. Second person, stand beside the wearer, one big step apart.", args.quiet)
    time.sleep(args.settle + 2)
    stages["pair"] = sample(args.host, args.hold)
    speak("Finished. Thank you.", args.quiet)

    worn = [s for name, group in stages.items() if name != "pair" for s in group]
    reach = [d for d in args.distances if share(stages[f"at_{d:g}"], matched) >= 0.9]
    rates = [s["rate"] for group in stages.values() for s in group]
    when = date.today().isoformat()
    pace = round(sum(len(group) for group in stages.values()) / (args.hold * len(stages)))
    setup = f"{args.place}, {args.hold:g} second hold at each spot, state read about {pace} times a second, {when}"
    measured = []
    if reach:
        measured.append({"number": f"{max(reach):g} m", "what": "Farthest spot where the badge was matched at least 90 percent of the time", "conditions": f"One person, tested at {', '.join(f'{d:g}' for d in args.distances)} m, {setup}"})
    measured.append({"number": f"{sum(1 for s in worn if not hidden(s))} of {len(worn)}", "what": "Checks where the badge wearer was left uncovered", "conditions": f"One person with the badge on, every distance plus back turned, {setup}"})
    measured.append({"number": percent(share(stages["back"], hidden)), "what": "Of checks kept the wearer hidden with their back turned", "conditions": f"Badge light out of sight at 2 m, {setup}"})
    measured.append({"number": percent(share(stages["pair"], matched)), "what": "Of checks erased exactly one person when two stood side by side", "conditions": f"Wearer and a second person about one step apart at 2 m, {setup}"})
    if rates:
        measured.append({"number": f"{round(sum(rates) / len(rates))}", "what": "Frames a second while erasing", "conditions": f"Raspberry Pi 5, 1280 by 720 video, {when}"})
    if args.tests:
        measured.append({"number": str(args.tests), "what": "Automated tests passing", "conditions": f"pytest, {when}"})

    raw = Path(args.raw)
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(json.dumps({"when": when, "stages": stages}))
    Path(args.out).write_text(json.dumps({"measured": measured}, indent=2) + "\n")
    for name, group in stages.items():
        print(name, len(group), "checks, matched", percent(share(group, matched)), "hidden", percent(share(group, hidden)))
    for entry in measured:
        print(entry["number"], "|", entry["what"])


if __name__ == "__main__":
    main()
