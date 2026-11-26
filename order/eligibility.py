from dataclasses import dataclass

from call.support import Problem, text
from script.order import is_earlier_cue


@dataclass(frozen=True)
class AmendmentScope:
    session: str
    target: str
    predecessor: str
    target_terminal: str
    target_station: str
    predecessor_terminal: str
    predecessor_station: str


def check_amendment_scope(record, edition, target, predecessor):
    cues = {cue.cue: cue for cue in edition.cues}
    target_cue = cues.get(text(target))
    predecessor_cue = cues.get(text(predecessor))
    if target_cue is None or predecessor_cue is None:
        raise Problem(404, 'unknown_cue')
    if not is_earlier_cue(predecessor_cue, target_cue):
        raise Problem(400, 'invalid_predecessor')
    bindings = {binding.role: binding for binding in record.bindings}
    target_binding = bindings.get(target_cue.role)
    predecessor_binding = bindings.get(predecessor_cue.role)
    if target_binding is None or predecessor_binding is None:
        raise Problem(400, 'cue_has_no_terminal')
    return AmendmentScope(record.session, target, predecessor, target_binding.terminal,
                          target_binding.station, predecessor_binding.terminal,
                          predecessor_binding.station)
