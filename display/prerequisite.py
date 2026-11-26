from dataclasses import dataclass

from call.support import Unavailable
from display.receipt import Receipt, lookup_receipt


@dataclass(frozen=True)
class PredecessorIdentity:
    session: str
    terminal: str
    station: str
    cue: str

    @classmethod
    def from_rule(cls, rule):
        return cls(rule['session'], rule['predecessor_terminal'], rule['predecessor_station'],
                   rule['predecessor'])


def matches_appearance(identity: PredecessorIdentity, receipt: Receipt | None) -> bool:
    if receipt is None:
        return False
    return identity == PredecessorIdentity(receipt.session, receipt.terminal, receipt.station, receipt.cue)


def read_predecessor(ledger, terminals, rule):
    identity = PredecessorIdentity.from_rule(rule)
    if identity.station == ledger.station:
        return lookup_receipt(ledger, identity.session, identity.terminal, cue=identity.cue)
    try:
        result = terminals.request(identity.station, 'appearance', {
            'session': identity.session, 'terminal': identity.terminal, 'cue': identity.cue,
        })
    except Unavailable:
        return None
    return Receipt.from_payload(result.get('receipt'))
