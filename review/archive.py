import json
from dataclasses import asdict, dataclass

from call.support import database, encode
from review.coverage import RoleCoverage


@dataclass(frozen=True)
class ExcerptRecord:
    excerpt: str
    content: dict

    def to_payload(self):
        return dict(self.content, excerpt=self.excerpt)


class ExcerptArchive:
    def __init__(self, path):
        self.path = path
        with database(path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS excerpts (
                id INTEGER PRIMARY KEY, session TEXT NOT NULL, content TEXT NOT NULL
            )''')

    def issue(self, session, edition, coverage: list[RoleCoverage]) -> ExcerptRecord:
        content = {'session': session, 'edition': edition, 'roles': [asdict(role) for role in coverage]}
        with database(self.path, write=True) as db:
            number = db.execute('INSERT INTO excerpts(session, content) VALUES (?, ?)',
                                (session, encode(content))).lastrowid
        return ExcerptRecord(f'X{number}', content)

    def find(self, session, excerpt):
        with database(self.path) as db:
            row = db.execute("SELECT content FROM excerpts WHERE session = ? AND 'X' || id = ?",
                             (session, excerpt)).fetchone()
        if row is None:
            return None
        return ExcerptRecord(excerpt, json.loads(row['content']))
