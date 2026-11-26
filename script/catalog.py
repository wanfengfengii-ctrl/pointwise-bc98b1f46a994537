import json
from dataclasses import asdict, dataclass

from call.support import database, encode
from script.parse import CueDraft, ScriptDraft


@dataclass(frozen=True)
class Edition:
    edition: str
    script: str
    roles: tuple[str, ...]
    cues: tuple[CueDraft, ...]


class EditionCatalog:
    def __init__(self, path):
        self.path = path
        with database(path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS editions (
                id INTEGER PRIMARY KEY, content TEXT NOT NULL
            )''')

    def create(self, draft: ScriptDraft) -> Edition:
        with database(self.path, write=True) as db:
            number = db.execute('INSERT INTO editions(content) VALUES (?)',
                                (encode(asdict(draft)),)).lastrowid
        return Edition(f'V{number}', draft.script, draft.roles, draft.cues)

    def find(self, edition: str) -> Edition | None:
        with database(self.path) as db:
            row = db.execute("SELECT content FROM editions WHERE 'V' || id = ?", (edition,)).fetchone()
        if row is None:
            return None
        data = json.loads(row['content'])
        return Edition(edition, data['script'], tuple(data['roles']),
                       tuple(CueDraft(**cue) for cue in data['cues']))
