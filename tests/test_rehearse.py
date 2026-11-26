from tests.fixture import RehearsalCase


class RehearsalTests(RehearsalCase):
    def setUp(self):
        super().setUp()
        self.open_sample()

    def test_old_show_waits_after_amendment(self):
        target = self.preload('right', 'B1', 'PB')
        source = self.preload('left', 'A1', 'PA')
        held = self.arm('right', 'show', 'before_commit', 'hold', 'PB')
        running = self.background_show(target, held)
        self.assertEqual(self.amend()['status'], 'applied')
        self.assertEqual(self.lookup('amendment', 'M')['status'], 'applied')
        self.assertEqual(self.ledger('left'), [])
        unrelated = self.display('right', 'B0', 'PB0')
        held.resume.set()
        waited = running.result(timeout=5)
        self.assertEqual(waited['status'], 'waiting', 'PRELOADED_TARGET_SHOWN_BEFORE_PREDECESSOR')
        self.assertEqual(self.ledger('right'), [unrelated])
        self.error(404, 'unknown_record', 'lookup', session=self.session, kind='receipt', id='PB')
        self.assertEqual(self.post('show', **source)['status'], 'shown')
        shown = self.post('show', **target)
        self.assertEqual((shown['status'], shown['receipt']['request'], shown['receipt']['sequence']),
                         ('shown', 'PB', 2))
        self.assertEqual(self.post('show', **target), shown)
        self.assertEqual(self.ledger('right'), [unrelated, shown['receipt']])

    def test_preload_identity_and_original_replay(self):
        target = self.preload('right', 'B1', 'PB')
        self.error(404, 'unknown_session', 'preload', **dict(target, session='S999'))
        self.error(404, 'cue_not_on_sheet', 'preload', **dict(target, terminal='left'))
        self.error(404, 'cue_not_on_sheet', 'preload', **dict(target, cue='missing'))
        self.error(409, 'preload_request_conflict', 'preload', **dict(target, cue='B0'))
        self.error(409, 'preload_request_conflict', 'show', **dict(target, cue='B0'))
        self.error(404, 'unknown_record', 'show', **dict(target, request='missing'))
        self.assertEqual(self.ledger('right'), [])
        self.assertEqual(self.post('preload', **target)['request'], 'PB')
        self.assertEqual(self.post('show', **target)['receipt']['cue'], 'B1')

    def test_illegal_predecessor_leaves_original_rule_intact(self):
        target = self.preload('right', 'B1', 'PB')
        self.assertEqual(self.amend()['status'], 'applied')
        for cue, status, code in [('B1', 400, 'invalid_predecessor'), ('A2', 400, 'invalid_predecessor'),
                                  ('missing', 404, 'unknown_cue')]:
            with self.subTest(cue=cue):
                self.error(status, code, 'amend', session=self.session, target='B1', predecessor=cue,
                           request='bad')
        self.assertEqual(self.lookup('amendment', 'M')['predecessor'], 'A1')
        self.assertEqual(self.post('show', **target)['status'], 'waiting')
        self.assertEqual(self.ledger('right'), [])

    def test_waiting_show_recovers_after_predecessor_loss(self):
        target = self.preload('right', 'B1', 'PB')
        source = self.preload('left', 'A1', 'PA')
        self.assertEqual(self.amend()['status'], 'applied')
        self.assertEqual(self.post('show', **target)['status'], 'waiting', 'PRELOADED_TARGET_SHOWN_BEFORE_PREDECESSOR')
        held = self.arm('left', 'show', 'before_commit', 'hold', 'PA')
        running = self.background_show(source, held)
        self.assertEqual(self.ledger('left'), [])
        self.assertEqual(self.post('show', **target)['status'], 'waiting', 'UNCOMMITTED_PREDECESSOR_RELEASED_TARGET')
        self.assertEqual(self.ledger('right'), [])
        lost = self.arm('left', 'show', 'after', 'drop', 'PA')
        held.resume.set()
        with self.assertRaisesRegex(Exception, '^endpoint_unavailable$'):
            running.result(timeout=5)
        self.assertTrue(lost.entered.is_set())
        self.assertEqual(self.ledger('left'), [lost.result['receipt']])
        self.restart()
        original_source = self.lookup('receipt', 'PA')
        self.assertEqual(original_source, lost.result)
        self.assertEqual(self.post('show', **source), original_source)
        shown = self.post('show', **target)
        self.assertEqual(shown['status'], 'shown', 'COMMITTED_PREDECESSOR_DID_NOT_RELEASE_TARGET')
        self.assertEqual(shown['receipt']['request'], 'PB')
        self.assertEqual(self.post('show', **target), shown)
        self.assertEqual(self.lookup('receipt', 'PB'), shown)
        self.assertEqual(self.ledger('left'), [original_source['receipt']])
        self.assertEqual(self.ledger('right'), [shown['receipt']])

    def test_target_first_loses_reply_and_rejects_amendment(self):
        target = self.preload('right', 'B1', 'PB')
        lost = self.arm('right', 'show', 'after', 'drop', 'PB')
        self.error(503, 'endpoint_unavailable', 'show', **target)
        first = lost.result
        self.assertEqual((first['receipt']['cue'], first['receipt']['sequence']), ('B1', 1))
        for operation in (lambda: self.amend(), lambda: self.lookup('amendment', 'M')):
            blocked = self.arm('right', 'apply_amendment', 'before', 'unavailable', 'M')
            self.assertEqual(operation()['status'], 'pending', 'ORDER_APPLIED_BEFORE_CONFIRMATION')
            self.assertTrue(blocked.entered.is_set())
        second = self.display('right', 'B0', 'PB0')
        self.assertEqual(second['sequence'], 2)
        self.restart()
        decision = self.lookup('amendment', 'M')
        self.assertEqual((decision['status'], decision['reason']), ('rejected', 'already_shown'))
        self.assertEqual(self.amend(), decision)
        self.assertEqual(self.lookup('receipt', 'PB'), first)
        self.assertEqual(self.post('show', **target), first)
        self.assertEqual(self.ledger('right'), [first['receipt'], second])

    def test_same_text_does_not_satisfy_designated_predecessor(self):
        target = self.preload('right', 'B1', 'PB')
        self.assertEqual(self.amend()['status'], 'applied')
        other = self.display('left', 'A0', 'PA0')
        self.assertEqual((other['cue'], other['text']), ('A0', '门开了'))
        self.assertEqual(self.post('show', **target)['status'], 'waiting')
        self.assertEqual(self.ledger('right'), [])
        self.assertEqual([receipt['cue'] for receipt in self.ledger('left')], ['A0'])

    def test_amendment_after_commit_loss_recovers_same_decision(self):
        target = self.preload('right', 'B1', 'PB')
        lost = self.arm('right', 'apply_amendment', 'after', 'drop', 'M')
        self.assertEqual(self.amend()['status'], 'pending')
        self.assertEqual(lost.result['status'], 'applied')
        self.error(409, 'amendment_request_conflict', 'amend', session=self.session, target='B1',
                   predecessor='A0', request='M')
        self.assertEqual(self.post('show', **target)['status'], 'waiting')
        self.restart()
        original = self.lookup('amendment', 'M')
        self.assertEqual((original['status'], original['predecessor']), ('applied', 'A1'))
        self.assertEqual(self.amend(), original)
        replacement = self.amend(predecessor='A0', request='M2')
        self.assertEqual((replacement['status'], replacement['reason']), ('rejected', 'already_has_predecessor'))
        self.assertEqual(self.lookup('amendment', 'M'), original)

    def test_same_station_predecessor_and_duplicate_show(self):
        target = self.preload('right', 'B1', 'PB')
        another = self.preload('right', 'B1', 'PB-other')
        self.assertEqual(self.amend(predecessor='B0')['status'], 'applied')
        self.assertEqual(self.post('show', **target)['status'], 'waiting')
        first = self.display('right', 'B0', 'PB0')
        held = self.arm('right', 'show', 'before_commit', 'hold', 'PB')
        running = self.background_show(target, held)
        shown = self.post('show', **target)
        held.resume.set()
        self.assertEqual(running.result(timeout=5), shown)
        self.error(409, 'cue_already_shown', 'show', **another)
        self.assertEqual(self.ledger('right'), [first, shown['receipt']])
