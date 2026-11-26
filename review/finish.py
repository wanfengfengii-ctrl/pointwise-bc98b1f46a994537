import json
from dataclasses import asdict, dataclass

from call.support import Problem, Unavailable, database, encode, text
from review.archive import ExcerptRecord
from review.coverage import build_coverage
from review.reconcile import reconcile_session


@dataclass(frozen=True)
class FinishRecord:
    request: str
    session: str
    status: str
    excerpt: str | None = None

    def to_payload(self):
        return {'request': self.request, 'session': self.session, 'status': self.status}


class FinishStore:
    """Durable coordinator-side claim for a session's single final excerpt."""

    def __init__(self, path):
        self.path = path
        with database(path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS finish_requests (
                request TEXT PRIMARY KEY,
                session TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK(status IN ('pending', 'finished')),
                excerpt TEXT
            )''')

    @staticmethod
    def _from_row(row):
        if row is None:
            return None
        return FinishRecord(row['request'], row['session'], row['status'], row['excerpt'])

    def register(self, session, request):
        with database(self.path, write=True) as db:
            existing = self._from_row(db.execute(
                'SELECT request, session, status, excerpt FROM finish_requests WHERE request = ?',
                (request,),
            ).fetchone())
            if existing is not None:
                if existing.session != session:
                    raise Problem(409, 'finish_request_conflict')
                return existing
            same_session = db.execute(
                'SELECT 1 FROM finish_requests WHERE session = ?', (session,)
            ).fetchone()
            if same_session is not None:
                raise Problem(409, 'finish_request_conflict')
            db.execute("INSERT INTO finish_requests(request, session, status) VALUES (?, ?, 'pending')",
                       (request, session))
        return FinishRecord(request, session, 'pending')

    def complete(self, request, session, content):
        with database(self.path, write=True) as db:
            row = db.execute(
                'SELECT status, excerpt FROM finish_requests WHERE request = ? AND session = ?',
                (request, session),
            ).fetchone()
            if row is None:
                raise Problem(404, 'unknown_record')
            if row['status'] == 'finished':
                excerpt_id = row['excerpt']
                archive_row = db.execute(
                    "SELECT content FROM excerpts WHERE session = ? AND 'X' || id = ?",
                    (session, excerpt_id),
                ).fetchone()
                if archive_row is None:
                    raise Unavailable('final_excerpt_unavailable')
                return ExcerptRecord(excerpt_id, json.loads(archive_row['content']))

            cursor = db.execute('INSERT INTO excerpts(session, content) VALUES (?, ?)',
                                (session, encode(content)))
            excerpt_id = f'X{cursor.lastrowid}'
            db.execute('''UPDATE finish_requests
                          SET status = 'finished', excerpt = ?
                          WHERE request = ? AND session = ? AND status = 'pending' ''',
                       (excerpt_id, request, session))
            return ExcerptRecord(excerpt_id, content)


def verified_stop(answer, binding, session, request):
    if not isinstance(answer, dict):
        raise Unavailable('invalid_finish_result')
    expected = {
        'session': session,
        'terminal': binding.terminal,
        'station': binding.station,
        'request': request,
        'finished': True,
    }
    if any(answer.get(key) != value for key, value in expected.items()):
        raise Unavailable('invalid_finish_result')


def stop_both_terminals(record, terminals, request):
    failure = None
    for binding in record.bindings:
        payload = {'session': record.session, 'terminal': binding.terminal, 'request': request}
        try:
            answer = terminals.request(binding.station, 'finish', payload)
            verified_stop(answer, binding, record.session, request)
        except Unavailable as exc:
            if failure is None:
                failure = exc
        except Problem as exc:
            if failure is None:
                failure = Unavailable('incomplete_finish')
            failure.__cause__ = exc
    if failure is not None:
        raise failure


def build_last_sequences(reconciled):
    return {
        sheet.terminal: max((receipt.sequence for receipt in receipts), default=0)
        for sheet, receipts in reconciled.sources
    }


def finish_session(store, archive, terminals, record, edition, request):
    request = text(request)
    stored = store.register(record.session, request)
    if stored.status == 'finished':
        excerpt = archive.find(record.session, stored.excerpt)
        if excerpt is None:
            raise Unavailable('final_excerpt_unavailable')
        return {'status': 'finished', 'excerpt': excerpt.to_payload()}

    try:
        stop_both_terminals(record, terminals, request)
        reconciled = reconcile_session(record, edition, terminals)
    except Unavailable:
        return {'status': 'pending'}

    coverage = build_coverage(reconciled)
    content = {
        'session': reconciled.session,
        'edition': reconciled.edition,
        'roles': [asdict(role) for role in coverage],
        'last_sequences': build_last_sequences(reconciled),
    }
    excerpt = store.complete(request, record.session, content)
    return {'status': 'finished', 'excerpt': excerpt.to_payload()}
