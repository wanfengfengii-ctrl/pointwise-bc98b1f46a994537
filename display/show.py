from call.support import Problem, text
from display.preload import IDENTITY_FIELDS
from display.prerequisite import read_predecessor
from display.receipt import lookup_receipt


def show_cue(ledger, terminals, identity, before_commit=None):
    preload = ledger.get_preload(identity['request'])
    if preload is None:
        raise Problem(404, 'unknown_record')
    if any(preload[key] != identity[key] for key in IDENTITY_FIELDS):
        raise Problem(409, 'preload_request_conflict')
    receipt = lookup_receipt(ledger, preload['session'], preload['terminal'], request=preload['request'])
    if receipt is not None:
        return {'status': 'shown', 'receipt': receipt.to_payload()}
    rule = ledger.get_rule(preload['session'], preload['cue'])
    proof = read_predecessor(ledger, terminals, rule) if rule is not None else None
    if before_commit is not None:
        before_commit()
    receipt = ledger.append_appearance(preload, proof)
    if receipt is None:
        return dict(identity, status='waiting')
    return {'status': 'shown', 'receipt': receipt.to_payload()}


def forward_show(directory, terminals, session, terminal, cue, request):
    identity = {'session': text(session), 'terminal': text(terminal), 'cue': text(cue),
                'request': text(request)}
    saved = directory.resolve(session, request)
    if any(saved[key] != value for key, value in identity.items()):
        raise Problem(409, 'preload_request_conflict')
    return terminals.request(saved['station'], 'show', identity)
