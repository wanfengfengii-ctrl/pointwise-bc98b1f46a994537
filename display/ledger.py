import json

from call.support import Problem, database, encode
from display.prerequisite import PredecessorIdentity, matches_appearance
from display.receipt import Receipt


class TerminalLedger:
    def __init__(self, path, station):
        self.path = path
        self.station = station
        with database(path) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS preloads (
                    request TEXT PRIMARY KEY, session TEXT NOT NULL, terminal TEXT NOT NULL,
                    cue TEXT NOT NULL, text TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('preloaded', 'waiting', 'shown'))
                );
                CREATE TABLE IF NOT EXISTS appearances (
                    sequence INTEGER PRIMARY KEY, session TEXT NOT NULL, cue TEXT NOT NULL,
                    terminal TEXT NOT NULL, text TEXT NOT NULL,
                    request TEXT NOT NULL UNIQUE REFERENCES preloads(request), UNIQUE(session, cue)
                );
                CREATE INDEX IF NOT EXISTS appearances_by_session ON appearances(session, sequence);
                CREATE TABLE IF NOT EXISTS amendment_decisions (
                    request TEXT PRIMARY KEY, command TEXT NOT NULL, status TEXT NOT NULL, reason TEXT
                );
                CREATE TABLE IF NOT EXISTS cue_rules (
                    session TEXT NOT NULL, cue TEXT NOT NULL,
                    request TEXT NOT NULL REFERENCES amendment_decisions(request), PRIMARY KEY(session, cue)
                );
            ''')

    def _receipt(self, row):
        if row is None:
            return None
        return Receipt(station=self.station, **dict(row))

    def save_preload(self, preload):
        self.check_station(preload['station'])
        request = preload['request']
        values = {field: preload[field] for field in ('request', 'session', 'terminal', 'cue', 'text')}
        with database(self.path, write=True) as db:
            existing = db.execute('SELECT * FROM preloads WHERE request = ?', (request,)).fetchone()
            if existing is not None:
                if any(existing[key] != value for key, value in values.items()):
                    raise Problem(409, 'preload_request_conflict')
                return
            db.execute('''INSERT INTO preloads(request, session, terminal, cue, text, state)
                          VALUES (:request, :session, :terminal, :cue, :text, 'preloaded')''', values)

    def check_station(self, station):
        if station != self.station:
            raise Problem(409, 'wrong_station')

    def get_preload(self, request):
        with database(self.path) as db:
            row = db.execute('SELECT * FROM preloads WHERE request = ?', (request,)).fetchone()
        return dict(row) if row is not None else None

    def mark_waiting(self, db, request):
        db.execute("UPDATE preloads SET state = 'waiting' WHERE request = ? AND state = 'preloaded'",
                   (request,))

    def _read_rule(self, db, session, cue):
        row = db.execute('''SELECT decisions.command FROM cue_rules AS rules
                            JOIN amendment_decisions AS decisions USING(request)
                            WHERE rules.session = ? AND rules.cue = ?''', (session, cue)).fetchone()
        return json.loads(row['command']) if row is not None else None

    def get_rule(self, session, cue):
        with database(self.path) as db:
            return self._read_rule(db, session, cue)

    def apply_amendment(self, command):
        self.check_station(command['target_station'])
        request, session, cue = (command[key] for key in ('request', 'session', 'target'))
        with database(self.path, write=True) as db:
            existing = db.execute('SELECT * FROM amendment_decisions WHERE request = ?',
                                  (request,)).fetchone()
            if existing is not None:
                if json.loads(existing['command']) != command:
                    raise Problem(409, 'amendment_request_conflict')
                return {'command': command, 'status': existing['status'], 'reason': existing['reason']}
            appearance = db.execute('SELECT 1 FROM appearances WHERE session = ? AND cue = ?',
                                    (session, cue)).fetchone()
            reason = None
            if appearance is not None:
                reason = 'already_shown'
            elif self._read_rule(db, session, cue) is not None:
                reason = 'already_has_predecessor'
            status = 'applied' if reason is None else 'rejected'
            db.execute('INSERT INTO amendment_decisions VALUES (?, ?, ?, ?)',
                       (request, encode(command), status, reason))
            if status == 'applied':
                db.execute('INSERT INTO cue_rules VALUES (?, ?, ?)', (session, cue, request))
        return {'command': command, 'status': status, 'reason': reason}

    def append_appearance(self, preload, proof):
        session, cue, request = (preload[key] for key in ('session', 'cue', 'request'))
        with database(self.path, write=True) as db:
            prior = db.execute('SELECT * FROM appearances WHERE session = ? AND cue = ?',
                               (session, cue)).fetchone()
            if prior is not None:
                if prior['request'] != request:
                    raise Problem(409, 'cue_already_shown')
                return self._receipt(prior)
            # The network read precedes this transaction. Compare its immutable proof
            # with the rule in effect at the actual first-write boundary.
            rule = self._read_rule(db, session, cue)
            if rule is not None and not matches_appearance(PredecessorIdentity.from_rule(rule), proof):
                self.mark_waiting(db, request)
                return None
            number = db.execute('''INSERT INTO appearances(session, cue, terminal, text, request)
                                   VALUES (:session, :cue, :terminal, :text, :request)''', preload).lastrowid
            db.execute("UPDATE preloads SET state = 'shown' WHERE request = ?", (request,))
            row = db.execute('SELECT * FROM appearances WHERE sequence = ?', (number,)).fetchone()
            return self._receipt(row)

    def find_appearance(self, session, *, request=None, cue=None):
        if (request is None) == (cue is None):
            raise ValueError('Specify either request or cue')
        column, value = ('request', request) if request is not None else ('cue', cue)
        with database(self.path) as db:
            row = db.execute(f'SELECT * FROM appearances WHERE session = ? AND {column} = ?',
                             (session, value)).fetchone()
        return self._receipt(row)

    def list_appearances(self, session):
        with database(self.path) as db:
            rows = db.execute('SELECT * FROM appearances WHERE session = ? ORDER BY sequence',
                              (session,)).fetchall()
        return [self._receipt(row) for row in rows]
