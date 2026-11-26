from dataclasses import dataclass

from call.support import Problem, require_fields, text


STATIONS = ('left', 'right')


@dataclass(frozen=True)
class TerminalBinding:
    terminal: str
    role: str
    station: str


def validate_bindings(items, roles):
    if not isinstance(items, list) or len(items) != len(STATIONS):
        raise Problem(400, 'invalid_bindings')
    bindings = []
    for item in items:
        require_fields(item, ('terminal', 'role'), ('station',))
        terminal = text(item['terminal'])
        role = text(item['role'])
        station = text(item.get('station', terminal))
        if role not in roles or station not in STATIONS:
            raise Problem(400, 'invalid_bindings')
        bindings.append(TerminalBinding(terminal, role, station))
    for field in ('terminal', 'role', 'station'):
        if len({getattr(binding, field) for binding in bindings}) != len(STATIONS):
            raise Problem(400, 'invalid_bindings')
    return tuple(bindings)


def role_for_terminal(bindings, terminal):
    for binding in bindings:
        if binding.terminal == terminal:
            return binding.role
    raise Problem(404, 'unknown_terminal_for_session')
