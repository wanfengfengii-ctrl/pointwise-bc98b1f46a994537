import json

from tests.fixture import RehearsalCase, SAMPLES


class ReviewTests(RehearsalCase):
    def setUp(self):
        super().setUp()
        self.open_sample()

    def test_actual_order_and_frozen_excerpt_replay(self):
        a0 = self.display('left', 'A0', 'PA0')
        a1 = self.display('left', 'A1', 'PA')
        b0 = self.display('right', 'B0', 'PB0')
        b1 = self.display('right', 'B1', 'PB')
        excerpt = self.post('close', session=self.session)
        expected = json.loads((SAMPLES / 'expected-excerpt.json').read_text(encoding='utf-8'))
        self.assertEqual(excerpt, expected)
        self.assertEqual(excerpt['roles'][0]['shown'], [a0, a1])
        self.assertEqual(excerpt['roles'][1]['shown'], [b0, b1])
        self.restart()
        self.assertEqual(self.lookup('excerpt', excerpt['excerpt']), expected)
        later = self.display('left', 'A2', 'PA2')
        after = self.post('close', session=self.session)
        self.assertEqual(after['roles'][0]['shown'], [a0, a1, later])
        self.assertEqual(after['roles'][0]['missed'], [])
        self.assertNotEqual(after['excerpt'], excerpt['excerpt'])
        self.assertEqual(self.lookup('excerpt', excerpt['excerpt']), expected)

    def test_skipped_earlier_cue_still_counts_as_missed(self):
        shown = self.display('left', 'A0', 'PA0')
        excerpt = self.post('close', session=self.session)
        self.assertEqual(excerpt['roles'][0]['shown'], [shown])
        self.assertEqual(excerpt['roles'][0]['missed'], ['A1', 'A2'])

    def test_missing_ledger_defers_then_recovers(self):
        b0 = self.display('right', 'B0', 'PB0')
        cut = self.arm('right', 'ledger', 'before', 'unavailable')
        self.error(503, 'incomplete_review', 'close', session=self.session)
        self.assertTrue(cut.entered.is_set())
        self.error(404, 'unknown_record', 'lookup', session=self.session, kind='excerpt', id='X1')
        excerpt = self.post('close', session=self.session)
        self.assertEqual(excerpt['excerpt'], 'X1')
        self.assertEqual(excerpt['roles'][1]['shown'], [b0])
        self.assertEqual(excerpt['roles'][1]['missed'], ['B1', 'B2'])

    def test_reachable_empty_ledgers_allow_review(self):
        excerpt = self.post('close', session=self.session)
        self.assertEqual([(role['terminal'], role['shown'], role['missed']) for role in excerpt['roles']],
                         [('left', [], ['A1', 'A0', 'A2']), ('right', [], ['B0', 'B1', 'B2'])])

    def test_lookup_requires_correct_session_and_type(self):
        appearance = self.display('left', 'A0', 'PA0')
        amendment = self.amend()
        excerpt = self.post('close', session=self.session)
        other = self.post('open', edition=self.edition, bindings=self.sample['bindings'])['session']
        for kind, record_id in [('receipt', 'PA0'), ('amendment', 'M'), ('excerpt', excerpt['excerpt'])]:
            self.error(404, 'unknown_record', 'lookup', session=other, kind=kind, id=record_id)
        self.error(404, 'unknown_record', 'lookup', session=self.session, kind='receipt', id=excerpt['excerpt'])
        self.error(404, 'unknown_record', 'lookup', session=self.session, kind='excerpt', id='M')
        self.error(404, 'unknown_record', 'lookup', session=self.session, kind='untyped', id='PA0')
        self.assertEqual(self.lookup('receipt', 'PA0')['receipt'], appearance)
        self.assertEqual(self.lookup('amendment', 'M'), amendment)
        self.assertEqual(self.lookup('excerpt', excerpt['excerpt']), excerpt)
