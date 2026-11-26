import json
from dataclasses import dataclass

from call.support import Problem, database, encode


@dataclass(frozen=True)
class AmendmentRecord:
    command: dict
    status: str
    reason: str | None = None

    def to_payload(self):
        result = {key: self.command[key] for key in ('session', 'request', 'target', 'predecessor')}
        result['status'] = self.status
        if self.reason is not None:
            result['reason'] = self.reason
        return result


def from_row(row):
    if row is None:
        return None
    return AmendmentRecord(json.loads(row['command']), row['status'], row['reason'])


class AmendmentStore:
    def __init__(self, path):
        self.path = path
        with database(path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS amendments (
                request TEXT PRIMARY KEY, session TEXT NOT NULL, command TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'applied', 'rejected')), reason TEXT
            )''')

    def register(self, command):
        request = command['request']
        with database(self.path, write=True) as db:
            existing = from_row(db.execute('SELECT * FROM amendments WHERE request = ?',
                                           (request,)).fetchone())
            if existing is not None:
                if existing.command != command:
                    raise Problem(409, 'amendment_request_conflict')
                return existing
            db.execute('INSERT INTO amendments VALUES (?, ?, ?, ?, NULL)',
                       (request, command['session'], encode(command), 'pending'))
        return AmendmentRecord(command, 'pending')

    def find(self, session, request):
        with database(self.path) as db:
            return from_row(db.execute('SELECT * FROM amendments WHERE session = ? AND request = ?',
                                       (session, request)).fetchone())

    def record_result(self, record, status, reason):
        session = record.command['session']
        request = record.command['request']
        with database(self.path, write=True) as db:
            db.execute('''UPDATE amendments SET status = ?, reason = ?
                          WHERE session = ? AND request = ? AND status = 'pending' ''',
                       (status, reason, session, request))
            return from_row(db.execute('SELECT * FROM amendments WHERE session = ? AND request = ?',
                                       (session, request)).fetchone())
