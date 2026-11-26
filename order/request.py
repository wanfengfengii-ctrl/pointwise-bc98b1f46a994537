from dataclasses import asdict

from call.support import text
from order.eligibility import check_amendment_scope
from order.settle import settle_amendment


def submit_amendment(store, terminals, record, edition, target, predecessor, request):
    scope = check_amendment_scope(record, edition, target, predecessor)
    amendment = store.register(dict(asdict(scope), request=text(request)))
    return settle_amendment(store, terminals, amendment).to_payload()
