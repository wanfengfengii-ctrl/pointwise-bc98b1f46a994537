import json
from http.server import BaseHTTPRequestHandler

from call.support import Problem, ResponseLost, encode, require_fields


def decode_json_request(handler):
    try:
        length = int(handler.headers.get('Content-Length', ''))
    except ValueError as exc:
        raise Problem(400, 'invalid_content_length') from exc
    if length < 1 or length > 1_048_576:
        raise Problem(400, 'invalid_content_length')
    try:
        payload = json.loads(handler.rfile.read(length).decode('utf-8'))
    except (UnicodeError, ValueError) as exc:
        raise Problem(400, 'invalid_json') from exc
    if not isinstance(payload, dict):
        raise Problem(400, 'expected_object')
    return payload


def write_json_response(handler, status, payload):
    body = encode(payload).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def endpoint(fields, operation):
    names = fields.split()

    def invoke(payload):
        require_fields(payload, names)
        return operation(*(payload[name] for name in names))

    return invoke


def make_json_handler(routes):
    class JsonHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                operation = routes.get(self.path)
                if operation is None:
                    raise Problem(404, 'unknown_operation')
                result = operation(decode_json_request(self))
                status = 200
            except Problem as exc:
                status, result = exc.status, {'error': exc.code}
            except ResponseLost:
                self.close_connection = True
                return
            try:
                write_json_response(self, status, result)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

        def log_message(self, format, *args):
            return

    return JsonHandler


def make_public_handler(operations):
    return make_json_handler({f'/{name}': operation for name, operation in operations.items()})
