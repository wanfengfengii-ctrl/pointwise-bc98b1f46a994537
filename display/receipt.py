from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from display.ledger import TerminalLedger


@dataclass(frozen=True)
class Receipt:
    session: str
    terminal: str
    station: str
    cue: str
    request: str
    sequence: int
    text: str

    @classmethod
    def from_payload(cls, payload):
        strings = ('session', 'terminal', 'station', 'cue', 'request', 'text')
        if not isinstance(payload, dict) or payload.keys() != (set(strings) | {'sequence'}):
            return None
        if any(not isinstance(payload[key], str) or not payload[key].strip() for key in strings):
            return None
        if type(payload['sequence']) is not int or payload['sequence'] < 1:
            return None
        return cls(**payload)

    def to_payload(self):
        return asdict(self)


def lookup_receipt(ledger: 'TerminalLedger', session, terminal, *, request=None, cue=None):
    receipt = ledger.find_appearance(session, request=request, cue=cue)
    if receipt is not None and receipt.terminal == terminal:
        return receipt
    return None


def read_session_receipts(ledger: 'TerminalLedger', session, terminal):
    return {'session': session, 'terminal': terminal, 'station': ledger.station,
            'receipts': [receipt.to_payload() for receipt in ledger.list_appearances(session)]}
