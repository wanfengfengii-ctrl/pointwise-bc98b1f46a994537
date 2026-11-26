import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock

from call.runtime import local_rehearsal
from call.support import Problem, ResponseLost, Unavailable
from display.http_api import json_request


SAMPLES = Path(__file__).resolve().parents[1] / 'samples'


@dataclass
class Cut:
    mode: str
    entered: Event = field(default_factory=Event)
    resume: Event = field(default_factory=Event)
    result: dict | None = None


class Timeline:
    def __init__(self):
        self.lock = Lock()
        self.armed = {}

    def arm(self, station, operation, phase, mode, request):
        cut = Cut(mode)
        key = (station, operation, phase, request)
        with self.lock:
            if key in self.armed:
                raise RuntimeError('A cut already owns this operation')
            self.armed[key] = cut
        return cut

    def __call__(self, station, operation, phase, payload, result):
        key = (station, operation, phase, payload.get('request'))
        with self.lock:
            cut = self.armed.pop(key, None)
            if cut is None and key[3] is not None:
                cut = self.armed.pop((station, operation, phase, None), None)
        if cut is None:
            return
        cut.result = result
        cut.entered.set()
        if cut.mode == 'drop':
            raise ResponseLost()
        if cut.mode == 'unavailable':
            raise Unavailable()
        if cut.mode == 'hold' and not cut.resume.wait(8):
            raise RuntimeError('Timed out waiting for the test to release a held HTTP operation')


class RehearsalCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory(prefix='yuqiao-test-')))
        self.services = self.enterContext(ExitStack())
        self.pool = self.enterContext(ThreadPoolExecutor(max_workers=4))
        self.timeline = Timeline()
        self.sample = json.loads((SAMPLES / 'rehearsal.json').read_text(encoding='utf-8'))
        self.restart()

    def restart(self):
        self.services.close()
        self.address, self.terminals = self.services.enter_context(local_rehearsal(self.root, self.timeline))

    def post(self, operation, **payload):
        return json_request(self.address, f'/{operation}', payload)

    def error(self, status, code, operation, **payload):
        with self.assertRaises(Problem) as caught:
            self.post(operation, **payload)
        self.assertEqual((caught.exception.status, caught.exception.code), (status, code))

    def arm(self, station, operation, phase, mode, request=None):
        cut = self.timeline.arm(station, operation, phase, mode, request)
        self.addCleanup(cut.resume.set)
        return cut

    def background_show(self, identity, cut):
        future = self.pool.submit(self.post, 'show', **identity)
        self.assertTrue(cut.entered.wait(5), 'HTTP request did not reach the requested pause')
        return future

    def open_sample(self):
        self.edition = self.post('release', **self.sample['release'])['edition']
        self.session = self.post('open', edition=self.edition, bindings=self.sample['bindings'])['session']
        return self.session

    def preload(self, terminal, cue, request):
        identity = {'session': self.session, 'terminal': terminal, 'cue': cue, 'request': request}
        response = self.post('preload', **identity)
        self.assertEqual(response['status'], 'preloaded')
        self.assertEqual({key: response[key] for key in identity}, identity)
        return identity

    def display(self, terminal, cue, request):
        result = self.post('show', **self.preload(terminal, cue, request))
        self.assertEqual(result['status'], 'shown')
        return result['receipt']

    def ledger(self, station):
        return self.terminals.read_ledger(station, self.session, station)['receipts']

    def lookup(self, kind, record_id):
        return self.post('lookup', session=self.session, kind=kind, id=record_id)

    def amend(self, target='B1', predecessor='A1', request='M'):
        return self.post('amend', session=self.session, target=target, predecessor=predecessor, request=request)
