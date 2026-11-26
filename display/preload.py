import json

from call.cuesheet import CueSheet
from call.support import Problem, database, encode, text


IDENTITY_FIELDS = ('session', 'terminal', 'cue', 'request')


class PreloadDirectory:
    def __init__(self, path):
        self.path = path
        with database(path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS preload_directory (
                request TEXT PRIMARY KEY, session TEXT NOT NULL, payload TEXT NOT NULL
            )''')

    def reserve(self, payload):
        with database(self.path, write=True) as db:
            existing = db.execute('SELECT payload FROM preload_directory WHERE request = ?',
                                  (payload['request'],)).fetchone()
            if existing is not None:
                original = json.loads(existing['payload'])
                if original != payload:
                    raise Problem(409, 'preload_request_conflict')
                return original
            db.execute('INSERT INTO preload_directory VALUES (?, ?, ?)',
                       (payload['request'], payload['session'], encode(payload)))
        return payload

    def resolve(self, session, request):
        with database(self.path) as db:
            row = db.execute('SELECT payload FROM preload_directory WHERE session = ? AND request = ?',
                             (session, request)).fetchone()
        if row is None:
            raise Problem(404, 'unknown_record')
        return json.loads(row['payload'])


def accept_preload(directory, terminals, sheet: CueSheet, cue, request):
    cue, request = text(cue), text(request)
    selected = next((item for item in sheet.cues if item.cue == cue), None)
    if selected is None:
        raise Problem(404, 'cue_not_on_sheet')
    payload = directory.reserve({'session': sheet.session, 'terminal': sheet.terminal,
                                 'station': sheet.station, 'cue': cue, 'request': request,
                                 'text': selected.text})
    return terminals.request(sheet.station, 'preload', payload)


def store_preload(ledger, payload):
    ledger.save_preload(payload)
    response = {field: payload[field] for field in IDENTITY_FIELDS}
    return dict(response, status='preloaded', text=payload['text'])
