import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from call.http_api import make_json_handler
from call.support import Problem, Unavailable, encode, require_fields, text
from display.preload import IDENTITY_FIELDS, store_preload
from display.receipt import lookup_receipt, read_session_receipts
from display.show import show_cue


def json_request(base_url, route, payload):
    request = Request(base_url + route, data=encode(payload).encode('utf-8'),
                      headers={'Content-Type': 'application/json; charset=utf-8'}, method='POST')
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=10) as response:
            result = json.load(response)
    except HTTPError as exc:
        try:
            with exc:
                result = json.load(exc)
            code = result['error']
        except (HTTPException, OSError, ValueError, KeyError, TypeError) as invalid:
            raise Unavailable('invalid_endpoint_response') from invalid
        if exc.code == 503:
            raise Unavailable(code) from exc
        raise Problem(exc.code, code) from exc
    except (URLError, HTTPException, OSError) as exc:
        raise Unavailable() from exc
    except ValueError as exc:
        raise Unavailable('invalid_endpoint_response') from exc
    if not isinstance(result, dict):
        raise Unavailable('invalid_endpoint_response')
    return result


class TerminalClient:
    def __init__(self, addresses):
        self.addresses = addresses

    def request(self, station, action, payload):
        address = self.addresses.get(station)
        if address is None:
            raise Unavailable()
        return json_request(address, f'/terminal/{action}', payload)

    def read_ledger(self, station, session, terminal):
        return self.request(station, 'ledger', {'session': session, 'terminal': terminal})


def make_terminal_handler(ledger, terminals, hook=None):
    def notify(action, phase, payload, result=None):
        if hook is not None:
            hook(ledger.station, action, phase, payload, result)

    def route(action, fields, operation):
        def invoke(payload):
            require_fields(payload, fields)
            for value in payload.values():
                text(value)
            notify(action, 'before', payload)
            result = operation(payload)
            notify(action, 'after', payload, result)
            return result

        return invoke

    def show(payload):
        return show_cue(ledger, terminals, payload,
                        before_commit=lambda: notify('show', 'before_commit', payload))

    def finish(payload):
        return ledger.stop_session(
            payload['session'], payload['terminal'], payload['request'],
            before_commit=lambda: notify('finish', 'before_commit', payload),
        )

    def receipt(payload, key):
        original = lookup_receipt(ledger, payload['session'], payload['terminal'], **{key: payload[key]})
        return {'receipt': original.to_payload() if original is not None else None}

    routes = {
        'preload': route('preload', IDENTITY_FIELDS + ('station', 'text'),
                         lambda payload: store_preload(ledger, payload)),
        'show': route('show', IDENTITY_FIELDS, show),
        'finish': route('finish', ('session', 'terminal', 'request'), finish),
        'apply_amendment': route('apply_amendment', (
            'session', 'request', 'target', 'predecessor', 'target_terminal', 'target_station',
            'predecessor_terminal', 'predecessor_station',
        ), ledger.apply_amendment),
        'appearance': route('appearance', ('session', 'terminal', 'cue'),
                            lambda payload: receipt(payload, 'cue')),
        'receipt': route('receipt', ('session', 'terminal', 'request'),
                         lambda payload: receipt(payload, 'request')),
        'ledger': route('ledger', ('session', 'terminal'),
                        lambda payload: read_session_receipts(ledger, **payload)),
    }
    return make_json_handler({f'/terminal/{name}': handler for name, handler in routes.items()})
