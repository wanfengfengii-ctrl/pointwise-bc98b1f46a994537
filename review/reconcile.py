from dataclasses import dataclass

from call.cuesheet import CueSheet, build_cuesheet
from call.support import Problem, Unavailable
from display.receipt import Receipt


@dataclass(frozen=True)
class ReconciledSession:
    session: str
    edition: str
    sources: tuple[tuple[CueSheet, tuple[Receipt, ...]], ...]


def verified_receipts(sheet, ledger):
    source = (sheet.session, sheet.terminal, sheet.station)
    if tuple(ledger.get(key) for key in ('session', 'terminal', 'station')) != source:
        raise Unavailable('invalid_ledger_source')
    items = ledger.get('receipts')
    if not isinstance(items, list):
        raise Unavailable('invalid_ledger_source')
    expected = {cue.cue: cue.text for cue in sheet.cues}
    cues, requests, sequences = set(), set(), set()
    reconciled = []
    for item in items:
        receipt = Receipt.from_payload(item)
        if receipt is None or (receipt.session, receipt.terminal, receipt.station) != source:
            raise Unavailable('invalid_ledger_source')
        if expected.get(receipt.cue) != receipt.text:
            raise Unavailable('invalid_ledger_cue')
        if receipt.cue in cues or receipt.request in requests or receipt.sequence in sequences:
            raise Unavailable('duplicate_ledger_entry')
        cues.add(receipt.cue)
        requests.add(receipt.request)
        sequences.add(receipt.sequence)
        reconciled.append(receipt)
    return tuple(reconciled)


def reconcile_session(record, edition, terminals):
    sources = []
    requests = set()
    for binding in record.bindings:
        sheet = build_cuesheet(record, edition, binding.terminal)
        try:
            ledger = terminals.read_ledger(binding.station, record.session, binding.terminal)
        except Problem as exc:
            raise Unavailable('incomplete_review') from exc
        receipts = verified_receipts(sheet, ledger)
        received_requests = {receipt.request for receipt in receipts}
        if requests & received_requests:
            raise Unavailable('duplicate_ledger_entry')
        requests.update(received_requests)
        sources.append((sheet, receipts))
    return ReconciledSession(record.session, edition.edition, tuple(sources))
