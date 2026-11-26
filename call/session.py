from call.casting import validate_bindings
from call.support import Problem, text


def open_session(catalog, sessions, edition, bindings):
    frozen = catalog.find(text(edition))
    if frozen is None:
        raise Problem(404, 'unknown_edition')
    record = sessions.create(frozen.edition, validate_bindings(bindings, frozen.roles))
    return {'session': record.session, 'edition': record.edition}


def get_session_context(catalog, sessions, session):
    record = sessions.find(text(session))
    if record is None:
        raise Problem(404, 'unknown_session')
    frozen = catalog.find(record.edition)
    if frozen is None:
        raise Problem(503, 'session_edition_unavailable')
    return record, frozen
