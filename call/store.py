import json
from dataclasses import asdict, dataclass

from call.casting import TerminalBinding
from call.support import database, encode


@dataclass(frozen=True)
class SessionRecord:
    session: str
    edition: str
    bindings: tuple[TerminalBinding, ...]


class SessionStore:
    def __init__(self, path):
        self.path = path
        with database(path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY, edition TEXT NOT NULL, bindings TEXT NOT NULL
            )''')

    def create(self, edition, bindings):
        with database(self.path, write=True) as db:
            number = db.execute('INSERT INTO sessions(edition, bindings) VALUES (?, ?)',
                                (edition, encode([asdict(binding) for binding in bindings]))).lastrowid
        return SessionRecord(f'S{number}', edition, bindings)

    def find(self, session):
        with database(self.path) as db:
            row = db.execute("SELECT edition, bindings FROM sessions WHERE 'S' || id = ?",
                             (session,)).fetchone()
        if row is None:
            return None
        bindings = tuple(TerminalBinding(**item) for item in json.loads(row['bindings']))
        return SessionRecord(session, row['edition'], bindings)
