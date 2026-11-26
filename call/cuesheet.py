from dataclasses import asdict, dataclass

from call.casting import role_for_terminal
from call.store import SessionRecord
from call.support import text
from script.catalog import Edition
from script.parse import CueDraft


@dataclass(frozen=True)
class CueSheet:
    session: str
    edition: str
    terminal: str
    station: str
    role: str
    cues: tuple[CueDraft, ...]

    def to_payload(self):
        return asdict(self)


def build_cuesheet(record: SessionRecord, edition: Edition, terminal: str) -> CueSheet:
    role = role_for_terminal(record.bindings, text(terminal))
    binding = next(binding for binding in record.bindings if binding.role == role)
    cues = tuple(cue for cue in edition.cues if cue.role == role)
    return CueSheet(record.session, edition.edition, terminal, binding.station, role, cues)
