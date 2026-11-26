import argparse
import json
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from call.casting import STATIONS
from call.cuesheet import build_cuesheet
from call.http_api import endpoint, make_public_handler
from call.session import get_session_context, open_session
from call.store import SessionStore
from call.support import encode
from display.http_api import TerminalClient, json_request, make_terminal_handler
from display.ledger import TerminalLedger
from display.preload import PreloadDirectory, accept_preload
from display.show import forward_show
from order.request import submit_amendment
from order.store import AmendmentStore
from review.archive import ExcerptArchive
from review.close import close_session
from review.lookup import lookup_record
from script.catalog import EditionCatalog
from script.release import release_edition


@dataclass(frozen=True)
class RuntimeConfig:
    root: Path
    coordinator_port: int = 8760
    left_port: int = 8761
    right_port: int = 8762

    def port_for(self, station):
        return {'left': self.left_port, 'right': self.right_port}[station]

    def terminal_path(self, station):
        return self.root / f'{station}.sqlite3'

    def terminal_client(self):
        return TerminalClient({station: loopback_url(self.port_for(station)) for station in STATIONS})


def loopback_url(port):
    return f'http://127.0.0.1:{port}'


@dataclass(frozen=True)
class CoordinatorStores:
    catalog: EditionCatalog
    sessions: SessionStore
    amendments: AmendmentStore
    directory: PreloadDirectory
    archive: ExcerptArchive

    @classmethod
    def open(cls, root):
        root.mkdir(parents=True, exist_ok=True)
        path = root / 'coordinator.sqlite3'
        return cls(EditionCatalog(path), SessionStore(path), AmendmentStore(path),
                   PreloadDirectory(path), ExcerptArchive(path))


def initialize_databases(config):
    CoordinatorStores.open(config.root)
    for station in STATIONS:
        TerminalLedger(config.terminal_path(station), station)


def coordinator_handler(stores, terminals):
    def context(session):
        return get_session_context(stores.catalog, stores.sessions, session)

    def sheet(session, terminal):
        return build_cuesheet(*context(session), terminal).to_payload()

    def preload(session, terminal, cue, request):
        cuesheet = build_cuesheet(*context(session), terminal)
        return accept_preload(stores.directory, terminals, cuesheet, cue, request)

    def amend(session, target, predecessor, request):
        record, edition = context(session)
        return submit_amendment(stores.amendments, terminals, record, edition, target, predecessor, request)

    def close(session):
        return close_session(stores.archive, terminals, *context(session))

    operations = {
        'release': partial(release_edition, stores.catalog),
        'open': endpoint('edition bindings', partial(open_session, stores.catalog, stores.sessions)),
        'sheet': endpoint('session terminal', sheet),
        'preload': endpoint('session terminal cue request', preload),
        'amend': endpoint('session target predecessor request', amend),
        'show': endpoint('session terminal cue request', partial(forward_show, stores.directory, terminals)),
        'close': endpoint('session', close),
        'lookup': endpoint('session kind id', partial(lookup_record, stores.amendments,
                                                      stores.directory, stores.archive, terminals)),
    }
    return make_public_handler(operations)


def serve_coordinator(config):
    handler = coordinator_handler(CoordinatorStores.open(config.root), config.terminal_client())
    with ThreadingHTTPServer(('127.0.0.1', config.coordinator_port), handler) as server:
        server.serve_forever()


def serve_terminal(config, station):
    config.root.mkdir(parents=True, exist_ok=True)
    ledger = TerminalLedger(config.terminal_path(station), station)
    handler = make_terminal_handler(ledger, config.terminal_client())
    with ThreadingHTTPServer(('127.0.0.1', config.port_for(station)), handler) as server:
        server.serve_forever()


@contextmanager
def local_rehearsal(root, hook=None):
    config = RuntimeConfig(root)
    stores = CoordinatorStores.open(root)
    with ExitStack() as stack:
        servers = {station: stack.enter_context(ThreadingHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler))
                   for station in STATIONS}
        terminals = TerminalClient({station: loopback_url(server.server_port)
                                    for station, server in servers.items()})
        for station, server in servers.items():
            ledger = TerminalLedger(config.terminal_path(station), station)
            server.RequestHandlerClass = make_terminal_handler(ledger, terminals, hook)
        coordinator = stack.enter_context(ThreadingHTTPServer(('127.0.0.1', 0),
                                                               coordinator_handler(stores, terminals)))
        for server in (*servers.values(), coordinator):
            thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
            thread.start()
            stack.callback(thread.join)
            stack.callback(server.shutdown)
        yield loopback_url(coordinator.server_port), terminals


def demo():
    samples = Path(__file__).resolve().parents[1] / 'samples'
    sample = json.loads((samples / 'rehearsal.json').read_text(encoding='utf-8'))
    expected = json.loads((samples / 'expected-excerpt.json').read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='yuqiao-demo-') as directory:
        root = Path(directory)
        with local_rehearsal(root) as (address, _):
            api = partial(json_request, address)
            edition = api('/release', sample['release'])['edition']
            session = api('/open', {'edition': edition, 'bindings': sample['bindings']})['session']
            actions = {cue: {'session': session, 'terminal': terminal, 'cue': cue, 'request': request}
                       for terminal, cue, request in [('left', 'A0', 'PA0'), ('left', 'A1', 'PA'),
                                                       ('right', 'B0', 'PB0'), ('right', 'B1', 'PB')]}
            for payload in actions.values():
                api('/preload', payload)
            amendment = api('/amend', {'session': session, 'target': 'B1', 'predecessor': 'A1', 'request': 'M'})
            api('/show', actions['A0'])
            waiting = api('/show', actions['B1'])
            if amendment['status'] != 'applied' or waiting['status'] != 'waiting':
                raise RuntimeError('接白须等待指定引句')
            for cue in ('B0', 'A1', 'B1'):
                if api('/show', actions[cue])['status'] != 'shown':
                    raise RuntimeError(f'提示未实际亮出 {cue}')
            excerpt = api('/close', {'session': session})
        with local_rehearsal(root) as (address, _):
            restored = json_request(address, '/lookup', {'session': session, 'kind': 'excerpt',
                                                         'id': excerpt['excerpt']})
    if excerpt != expected or restored != expected:
        raise RuntimeError('实际摘录或重开复领与样例台账不符')
    print('POINTWISE_SCENARIO ' + encode({
        'case_id': 'v7', 'input': {'readthrough': sample, 'shown': ['A0', 'B0', 'A1', 'B1']},
        'expected': expected, 'actual': excerpt, 'downstream_expected': expected,
        'downstream_actual': restored, 'code_paths': ['display/ledger.py', 'review/reconcile.py',
                                                      'review/coverage.py', 'review/archive.py'],
        'oracle': '逐端按发出顺序手编端内序号，再以正式角色单逐项勾去四条已亮提示。',
    }))


def main(argv=None):
    parser = argparse.ArgumentParser(description='榆桥读剧联排服务')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--coordinator-port', type=int, default=8760)
    parser.add_argument('--left-port', type=int, default=8761)
    parser.add_argument('--right-port', type=int, default=8762)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init')
    commands.add_parser('demo')
    commands.add_parser('coordinator')
    terminal = commands.add_parser('terminal')
    terminal.add_argument('station', choices=STATIONS)
    args = parser.parse_args(argv)
    if args.command == 'demo':
        demo()
        return
    if args.root is None:
        parser.error('--root is required for persisted services')
    config = RuntimeConfig(args.root, args.coordinator_port, args.left_port, args.right_port)
    if args.command == 'init':
        initialize_databases(config)
    elif args.command == 'coordinator':
        serve_coordinator(config)
    else:
        serve_terminal(config, args.station)


if __name__ == '__main__':
    main()
