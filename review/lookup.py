from call.support import Problem, Unavailable, text
from display.receipt import Receipt
from order.lookup import lookup_amendment


def lookup_record(amendments, directory, archive, terminals, session, kind, record_id):
    session, kind, record_id = text(session), text(kind), text(record_id)
    if kind == 'amendment':
        return lookup_amendment(amendments, terminals, session, record_id)
    if kind == 'excerpt':
        excerpt = archive.find(session, record_id)
        if excerpt is None:
            raise Problem(404, 'unknown_record')
        return excerpt.to_payload()
    if kind != 'receipt':
        raise Problem(404, 'unknown_record')
    original = directory.resolve(session, record_id)
    answer = terminals.request(original['station'], 'receipt', {
        'session': session, 'terminal': original['terminal'], 'request': record_id,
    })
    raw_receipt = answer.get('receipt')
    if raw_receipt is None:
        raise Problem(404, 'unknown_record')
    receipt = Receipt.from_payload(raw_receipt)
    if receipt is None or any(getattr(receipt, key) != original[key] for key in original):
        raise Unavailable('invalid_receipt_source')
    return {'status': 'shown', 'receipt': receipt.to_payload()}
