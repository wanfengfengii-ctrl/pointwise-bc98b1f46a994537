from dataclasses import dataclass

from review.reconcile import ReconciledSession


@dataclass(frozen=True)
class RoleCoverage:
    role: str
    terminal: str
    station: str
    shown: list[dict]
    missed: list[str]


def build_coverage(reconciled: ReconciledSession) -> list[RoleCoverage]:
    coverage = []
    for sheet, receipts in reconciled.sources:
        by_sequence = sorted(receipts, key=lambda receipt: receipt.sequence)
        shown_cues = {receipt.cue for receipt in by_sequence}
        coverage.append(RoleCoverage(sheet.role, sheet.terminal, sheet.station,
                                     [receipt.to_payload() for receipt in by_sequence],
                                     [cue.cue for cue in sheet.cues if cue.cue not in shown_cues]))
    return coverage
