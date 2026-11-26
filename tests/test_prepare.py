from copy import deepcopy

from call.runtime import RuntimeConfig, initialize_databases
from tests.fixture import RehearsalCase


class PrepareTests(RehearsalCase):
    def test_interleaved_sheets_keep_original_order(self):
        draft = deepcopy(self.sample['release'])
        draft['cues'] = draft['cues'][:4]
        edition = self.post('release', **draft)['edition']
        session = self.post('open', edition=edition, bindings=self.sample['bindings'])['session']
        for terminal, role, expected in (
            ('left', '甲', [('A1', 10, '门开了'), ('A0', 30, '门开了')]),
            ('right', '乙', [('B0', 20, '我在'), ('B1', 40, '那就进来')]),
        ):
            sheet = self.post('sheet', session=session, terminal=terminal)
            self.assertEqual((sheet['edition'], sheet['session'], sheet['role']), (edition, session, role))
            self.assertEqual([(cue['cue'], cue['position'], cue['text']) for cue in sheet['cues']], expected)

    def test_duplicate_cue_keeps_prior_edition(self):
        self.open_sample()
        draft = deepcopy(self.sample['release'])
        draft['cues'][1]['cue'] = 'A1'
        self.error(400, 'duplicate_cue', 'release', **draft)
        self.error(404, 'unknown_edition', 'open', edition='V2', bindings=self.sample['bindings'])
        restored = self.post('open', edition=self.edition, bindings=self.sample['bindings'])
        right = self.post('sheet', session=restored['session'], terminal='right')
        self.assertEqual([cue['cue'] for cue in right['cues']], ['B0', 'B1', 'B2'])

    def test_invalid_integer_positions_reject_whole_edition(self):
        for value in (10, 5, 10.5, True, None, '20'):
            with self.subTest(value=value):
                draft = deepcopy(self.sample['release'])
                draft['cues'][1]['position'] = value
                self.error(400, 'invalid_position', 'release', **draft)
        draft = deepcopy(self.sample['release'])
        del draft['cues'][1]['position']
        self.error(400, 'invalid_position', 'release', **draft)
        self.assertEqual(self.post('release', **self.sample['release'])['edition'], 'V1')

    def test_undeclared_role_rejects_whole_edition(self):
        self.open_sample()
        draft = deepcopy(self.sample['release'])
        draft['cues'][-1]['role'] = '丙'
        self.error(400, 'invalid_role', 'release', **draft)
        self.error(404, 'unknown_edition', 'open', edition='V2', bindings=self.sample['bindings'])
        sheet = self.post('sheet', session=self.session, terminal='right')
        self.assertEqual([cue['cue'] for cue in sheet['cues']], ['B0', 'B1', 'B2'])

    def test_invalid_bindings_do_not_open_session(self):
        bindings = self.sample['bindings']
        self.error(404, 'unknown_edition', 'open', edition='V1', bindings=bindings)
        edition = self.post('release', **self.sample['release'])['edition']
        for second in ({'terminal': 'left', 'role': '乙', 'station': 'right'},
                       {'terminal': 'right', 'role': '甲'}, {'terminal': 'right', 'role': '丙'},
                       {'terminal': 'right', 'role': '乙', 'station': 'left'},
                       {'terminal': 'right', 'role': '乙', 'station': 'third'}):
            with self.subTest(second=second):
                self.error(400, 'invalid_bindings', 'open', edition=edition, bindings=[bindings[0], second])
        self.assertEqual(self.post('open', edition=edition, bindings=bindings)['session'], 'S1')

    def test_empty_role_and_implicit_positions(self):
        draft = {'script': 'R2', 'roles': ['甲', '乙'], 'cues': [
            {'cue': 'A1', 'role': '甲', 'text': '一句'}, {'cue': 'A2', 'role': '甲', 'text': '二句'},
        ]}
        edition = self.post('release', **draft)['edition']
        session = self.post('open', edition=edition, bindings=self.sample['bindings'])['session']
        self.assertEqual(self.post('sheet', session=session, terminal='right')['cues'], [])
        left = self.post('sheet', session=session, terminal='left')
        self.assertEqual([cue['position'] for cue in left['cues']], [1, 2])

    def test_other_sessions_terminal_name_is_rejected(self):
        self.open_sample()
        alternate = [{'terminal': 'left-other', 'station': 'left', 'role': '甲'}, self.sample['bindings'][1]]
        other = self.post('open', edition=self.edition, bindings=alternate)['session']
        self.error(404, 'unknown_terminal_for_session', 'sheet', session=self.session, terminal='left-other')
        self.error(404, 'unknown_terminal_for_session', 'sheet', session=other, terminal='left')
        self.assertEqual(self.post('sheet', session=other, terminal='left-other')['role'], '甲')

    def test_session_keeps_edition_after_revision(self):
        self.open_sample()
        changed = deepcopy(self.sample['release'])
        changed['cues'][0]['text'] = '现在开门'
        changed['cues'][0]['position'] = 5
        newer = self.post('release', **changed)['edition']
        other = self.post('open', edition=newer, bindings=self.sample['bindings'])['session']
        old_sheet = self.post('sheet', session=self.session, terminal='left')
        new_sheet = self.post('sheet', session=other, terminal='left')
        self.assertEqual((old_sheet['edition'], old_sheet['cues'][0]['position'], old_sheet['cues'][0]['text']),
                         ('V1', 10, '门开了'))
        self.assertEqual((new_sheet['edition'], new_sheet['cues'][0]['position'], new_sheet['cues'][0]['text']),
                         ('V2', 5, '现在开门'))

    def test_repeat_init_preserves_custom_revision_and_session(self):
        self.open_sample()
        changed = deepcopy(self.sample['release'])
        changed['cues'][1]['text'] = '用户修订'
        custom = self.post('release', **changed)['edition']
        session = self.post('open', edition=custom, bindings=self.sample['bindings'])['session']
        before = [self.post('sheet', session=session, terminal=terminal) for terminal in ('left', 'right')]
        self.services.close()
        for _ in range(2):
            initialize_databases(RuntimeConfig(self.root))
        self.restart()
        self.assertEqual([self.post('sheet', session=session, terminal=terminal)
                          for terminal in ('left', 'right')], before)
        self.assertEqual(before[1]['cues'][0]['text'], '用户修订')
        self.assertEqual(self.post('release', **changed)['edition'], 'V3')
        self.assertEqual(self.post('open', edition=custom, bindings=self.sample['bindings'])['session'], 'S3')
