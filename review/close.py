from review.coverage import build_coverage
from review.reconcile import reconcile_session


def close_session(archive, terminals, record, edition):
    reconciled = reconcile_session(record, edition, terminals)
    coverage = build_coverage(reconciled)
    return archive.issue(reconciled.session, reconciled.edition, coverage).to_payload()
