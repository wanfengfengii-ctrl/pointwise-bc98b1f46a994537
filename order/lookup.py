from call.support import Problem
from order.settle import settle_amendment


def lookup_amendment(store, terminals, session, request):
    record = store.find(session, request)
    if record is None:
        raise Problem(404, 'unknown_record')
    return settle_amendment(store, terminals, record).to_payload()
