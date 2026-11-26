from finish_fixture import terminal_traffic
from call.support import Problem, Unavailable
from tests.fixture import RehearsalCase, Timeline


class FinishTests(RehearsalCase):
    def other_right_session(self, request='PO', cue='B1'):
        other = self.post('open', edition=self.edition, bindings=self.sample['bindings'])['session']
        identity = {'session': other, 'terminal': 'right', 'cue': cue, 'request': request}
        self.post('preload', **identity)
        receipt = self.post('show', **identity)['receipt']
        self.assertEqual((receipt['session'], receipt['sequence']), (other, 1))
        return other, identity, receipt

    def test_stop_rejects_in_flight_first_show_and_replays_original(self):
        self.open_sample()
        pa = self.display('left', 'A1', 'PA')
        target = self.preload('right', 'B1', 'PB')
        self.assertEqual(self.amend()['status'], 'applied')
        other, _, other_receipt = self.other_right_session()
        self.assertEqual(other_receipt['sequence'], 1)

        held = self.arm('right', 'show', 'before_commit', 'hold', 'PB')
        running = self.background_show(target, held)

        finished = self.post('finish', session=self.session, request='FS1')
        excerpt = finished['excerpt']
        self.assertEqual(finished['status'], 'finished')
        self.assertEqual(excerpt['excerpt'], 'X1')
        self.assertEqual(excerpt['last_sequences'], {'left': 1, 'right': 0})
        self.assertEqual(excerpt['roles'][0]['shown'], [pa])
        self.assertEqual(excerpt['roles'][0]['missed'], ['A0', 'A2'])
        self.assertEqual(excerpt['roles'][1]['shown'], [])
        self.assertEqual(excerpt['roles'][1]['missed'], ['B0', 'B1', 'B2'])

        held.resume.set()
        with self.assertRaises(Problem) as caught:
            running.result(timeout=5)
        self.assertEqual(caught.exception.status, 409)
        self.error(409, 'session_finished', 'show', **target)
        self.assertEqual(self.post('show', **self.preload('left', 'A1', 'PA')),
                         {'status': 'shown', 'receipt': pa})

        other_late = {'session': other, 'terminal': 'right', 'cue': 'B0', 'request': 'PO0'}
        self.post('preload', **other_late)
        self.assertEqual(self.post('show', **other_late)['receipt']['sequence'], 2)

        self.assertEqual(self.post('finish', session=self.session, request='FS1'), finished)
        self.restart()
        self.assertEqual(self.post('finish', session=self.session, request='FS1'), finished)
        self.assertEqual(self.lookup('excerpt', 'X1'), excerpt)

    def test_committed_first_show_is_included_with_session_sequence(self):
        self.open_sample()
        pa = self.display('left', 'A1', 'PA')
        target = self.preload('right', 'B1', 'PB')
        self.amend()
        self.other_right_session()

        held = self.arm('right', 'show', 'before_commit', 'hold', 'PB')
        running = self.background_show(target, held)
        held.resume.set()
        shown = running.result(timeout=5)
        self.assertEqual((shown['status'], shown['receipt']['sequence']), ('shown', 2))

        finished = self.post('finish', session=self.session, request='FS1')
        excerpt = finished['excerpt']
        self.assertEqual(excerpt['last_sequences'], {'left': 1, 'right': 2})
        self.assertEqual(excerpt['roles'][0]['shown'], [pa])
        self.assertEqual(excerpt['roles'][1]['shown'], [shown['receipt']])
        self.assertEqual(excerpt['roles'][1]['missed'], ['B0', 'B2'])

        self.restart()
        self.assertEqual(self.post('finish', session=self.session, request='FS1'), finished)

    def test_lost_first_receipt_still_replays_after_finish(self):
        self.open_sample()
        target = self.preload('right', 'B1', 'PB')
        traffic = Timeline()
        self.enterContext(terminal_traffic(traffic))
        lost = traffic.arm('right', 'show', 'after', 'drop', 'PB')

        with self.assertRaises(Unavailable):
            self.post('show', **target)
        original = lost.result
        self.assertEqual(original['status'], 'shown')

        finished = self.post('finish', session=self.session, request='FS1')
        self.assertEqual(finished['excerpt']['roles'][1]['shown'], [original['receipt']])
        self.assertEqual(finished['excerpt']['last_sequences']['right'], 1)
        self.assertEqual(self.post('show', **target), original)

        self.restart()
        self.assertEqual(self.post('show', **target), original)
        self.assertEqual(self.post('finish', session=self.session, request='FS1'), finished)

    def test_lost_seal_reply_is_pending_then_same_request_resumes_after_restart(self):
        self.open_sample()
        pa = self.display('left', 'A1', 'PA')
        traffic = Timeline()
        self.enterContext(terminal_traffic(traffic))
        lost = traffic.arm('right', 'finish', 'after', 'drop', 'FS1')

        pending = self.post('finish', session=self.session, request='FS1')
        self.assertEqual(pending, {'status': 'pending'})
        self.assertTrue(lost.entered.is_set())
        self.error(409, 'finish_request_conflict', 'finish', session=self.session, request='FS2')
        other = self.post('open', edition=self.edition, bindings=self.sample['bindings'])['session']
        self.error(409, 'finish_request_conflict', 'finish', session=other, request='FS1')

        self.restart()
        finished = self.post('finish', session=self.session, request='FS1')
        self.assertEqual(finished['status'], 'finished')
        excerpt = finished['excerpt']
        self.assertEqual(excerpt['last_sequences'], {'left': 1, 'right': 0})
        self.assertEqual(excerpt['roles'][0]['shown'], [pa])

        self.restart()
        self.assertEqual(self.post('finish', session=self.session, request='FS1'), finished)

    def test_one_final_excerpt_per_session_and_observation_close_remains(self):
        self.open_sample()
        pa0 = self.display('left', 'A0', 'PA0')
        observation = self.post('close', session=self.session)
        self.assertEqual(observation['excerpt'], 'X1')
        self.assertNotIn('last_sequences', observation)

        finished = self.post('finish', session=self.session, request='FS1')
        final = finished['excerpt']
        self.assertEqual(final['excerpt'], 'X2')
        self.assertEqual(final['last_sequences'], {'left': 1, 'right': 0})
        self.assertEqual(final['roles'][0]['shown'], [pa0])

        after_close = self.post('close', session=self.session)
        self.assertEqual(after_close['excerpt'], 'X3')
        self.assertNotIn('last_sequences', after_close)

        self.assertEqual(self.post('finish', session=self.session, request='FS1'), finished)
        self.error(409, 'finish_request_conflict', 'finish', session=self.session, request='FS2')
        other = self.post('open', edition=self.edition, bindings=self.sample['bindings'])['session']
        self.error(409, 'finish_request_conflict', 'finish', session=other, request='FS1')

        self.restart()
        self.assertEqual(self.lookup('excerpt', observation['excerpt']), observation)
        self.assertEqual(self.lookup('excerpt', final['excerpt']), final)
        self.assertEqual(self.lookup('excerpt', after_close['excerpt']), after_close)
        self.assertEqual(self.post('finish', session=self.session, request='FS1'), finished)

    def test_finish_validation_and_custom_terminal_sequence_keys(self):
        self.open_sample()
        self.error(404, 'unknown_session', 'finish', session='S999', request='FS1')
        with self.assertRaises(Problem) as caught:
            self.post('finish', session=self.session)
        self.assertEqual(caught.exception.status, 400)
        with self.assertRaises(Problem) as caught:
            self.post('finish', session=self.session, request='')
        self.assertEqual(caught.exception.status, 400)

        bindings = [
            {'terminal': '左台', 'role': '甲', 'station': 'left'},
            {'terminal': '右台', 'role': '乙', 'station': 'right'},
        ]
        custom = self.post('open', edition=self.edition, bindings=bindings)['session']
        identity = {'session': custom, 'terminal': '左台', 'cue': 'A1', 'request': 'P-CUSTOM'}
        self.post('preload', **identity)
        receipt = self.post('show', **identity)['receipt']
        finished = self.post('finish', session=custom, request='FC1')
        self.assertEqual(finished['excerpt']['last_sequences'], {'左台': 1, '右台': 0})
        self.assertEqual(finished['excerpt']['roles'][0]['shown'], [receipt])
