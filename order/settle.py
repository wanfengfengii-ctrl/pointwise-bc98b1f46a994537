from call.support import Unavailable
from order.store import AmendmentRecord, AmendmentStore


def settle_amendment(store: AmendmentStore, terminals, record: AmendmentRecord) -> AmendmentRecord:
    if record.status != 'pending':
        return record
    command = record.command
    try:
        decision = terminals.request(command['target_station'], 'apply_amendment', command)
    except Unavailable:
        return store.find(command['session'], command['request'])
    status, reason = decision.get('status'), decision.get('reason')
    confirmed = ((status == 'applied' and reason is None)
                 or (status == 'rejected' and reason in ('already_shown', 'already_has_predecessor')))
    if decision.get('command') != command or not confirmed:
        return store.find(command['session'], command['request'])
    return store.record_result(record, status, reason)
