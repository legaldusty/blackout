from dataclasses import dataclass
from typing import Protocol

from eye.beacon import CODE_COUNT, Policy

BEACON_PREFIX = bytes((0x4E, 0x50, 0x02))
COMPANY_ID = 0xFFFF
HEARD_SECONDS = 1.5


@dataclass(frozen=True)
class Heard:
    sender: str
    code: int
    policy: Policy


class Radio(Protocol):
    def heard(self, seconds: float) -> list[Heard]: ...


def parse_payload(sender: str, body: bytes) -> Heard | None:
    if len(body) != len(BEACON_PREFIX) + 2 or not body.startswith(BEACON_PREFIX):
        return None
    policy_byte, code = body[-2], body[-1]
    if code >= CODE_COUNT:
        return None
    try:
        policy = Policy(policy_byte)
    except ValueError:
        return None
    return Heard(sender, code, policy)


class Roster:
    def __init__(self, keep_seconds: float = HEARD_SECONDS):
        self.keep_seconds = keep_seconds
        self._last: dict[str, tuple[float, Heard]] = {}

    def note(self, seconds: float, heard: Heard) -> None:
        self._last[heard.sender] = (seconds, heard)

    def heard(self, seconds: float) -> list[Heard]:
        self._last = {k: v for k, v in self._last.items() if seconds - v[0] <= self.keep_seconds}
        return [entry for _, entry in self._last.values()]
