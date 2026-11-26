from dataclasses import replace

from call.support import Problem
from script.parse import CueDraft, ScriptDraft


def validate_script_order(draft: ScriptDraft) -> ScriptDraft:
    if len({cue.cue for cue in draft.cues}) != len(draft.cues):
        raise Problem(400, 'duplicate_cue')
    if all(cue.position is None for cue in draft.cues):
        cues = tuple(replace(cue, position=index) for index, cue in enumerate(draft.cues, 1))
        return replace(draft, cues=cues)
    previous = None
    for cue in draft.cues:
        if type(cue.position) is not int or (previous is not None and cue.position <= previous):
            raise Problem(400, 'invalid_position')
        previous = cue.position
    return draft


def is_earlier_cue(predecessor: CueDraft, target: CueDraft) -> bool:
    return predecessor.position < target.position
