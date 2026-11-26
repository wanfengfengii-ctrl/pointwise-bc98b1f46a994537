import json
import sqlite3
from contextlib import contextmanager


class Problem(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status = status
        self.code = code


class Unavailable(Problem):
    def __init__(self, code='endpoint_unavailable'):
        super().__init__(503, code)


class ResponseLost(Exception):
    pass


def require_fields(payload, required, optional=()):
    if not isinstance(payload, dict):
        raise Problem(400, 'expected_object')
    required = set(required)
    if not required <= payload.keys() or payload.keys() - (required | set(optional)):
        raise Problem(400, 'invalid_fields')


def text(value, code='invalid_identity'):
    if not isinstance(value, str) or not value.strip():
        raise Problem(400, code)
    return value


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


@contextmanager
def database(path, *, write=False):
    db = sqlite3.connect(path, isolation_level=None, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys = ON')
        if write:
            db.execute('BEGIN IMMEDIATE')
        yield db
        if write:
            db.commit()
    finally:
        db.close()
