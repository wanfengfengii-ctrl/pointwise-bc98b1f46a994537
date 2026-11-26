from dataclasses import dataclass

from call.support import Problem, require_fields, text


@dataclass(frozen=True)
class CueDraft:
    cue: str
    role: str
    text: str
    position: int | None = None


@dataclass(frozen=True)
class ScriptDraft:
    script: str
    roles: tuple[str, ...]
    cues: tuple[CueDraft, ...]


def parse_script(payload):
    require_fields(payload, ('script', 'roles', 'cues'))
    script = text(payload['script'])
    if not isinstance(payload['roles'], list) or not payload['roles']:
        raise Problem(400, 'invalid_roles')
    roles = tuple(text(role, 'invalid_role') for role in payload['roles'])
    if len(set(roles)) != len(roles):
        raise Problem(400, 'duplicate_role')
    if not isinstance(payload['cues'], list):
        raise Problem(400, 'invalid_cues')
    cues = []
    for item in payload['cues']:
        require_fields(item, ('cue', 'role', 'text'), ('position',))
        role = text(item['role'], 'invalid_role')
        if role not in roles:
            raise Problem(400, 'invalid_role')
        if 'position' in item and type(item['position']) is not int:
            raise Problem(400, 'invalid_position')
        cues.append(CueDraft(text(item['cue']), role, text(item['text'], 'invalid_cue_text'),
                             item.get('position')))
    return ScriptDraft(script, roles, tuple(cues))
