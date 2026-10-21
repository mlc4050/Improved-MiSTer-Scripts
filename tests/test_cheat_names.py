import runpy
import unittest
from pathlib import Path

compare = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                            'check_mister_cheats_v9.py'))['compare']


class CheatNameTests(unittest.TestCase):
    def match(self, title, cheat_title, system='nes', crc='4318A2F8'):
        cheat = dict(system=system, stem=cheat_title, crc=crc,
                     path=system + '/' + cheat_title + '.zip', issue='')
        game = dict(system='nes', stem=title, crc='A413EBC7', stripped='',
                    path='NES/Zapper/HDTV Hacks/' + title + '.nes')
        return compare([cheat], [game])

    def test_crc_tag_does_not_block_exact_name(self):
        for title in ("Barker Bill's Trick Shooting (USA)", 'Mega Man (USA)'):
            with self.subTest(title=title):
                rows, missing = self.match(title, title + ' [4318A2F8]')
                self.assertFalse(missing)
                self.assertEqual(rows[0]['status'], 'EXACT_NAME_MATCH')
                self.assertTrue(rows[0]['name_match'])
                self.assertFalse(rows[0]['crc_match'])

    def test_region_revision_hack_and_sequel_stay_distinct(self):
        for other in ('Mega Man (Japan)', 'Mega Man (USA) (Rev 1)',
                      'Mega Man (USA) [Hack]', 'Mega Man 2 (USA)'):
            rows, missing = self.match('Mega Man (USA)', other + ' [4318A2F8]')
            self.assertFalse(rows)
            self.assertEqual(len(missing), 1)

    def test_systems_stay_separate(self):
        rows, missing = self.match('Mega Man (USA)',
                                   'Mega Man (USA) [4318A2F8]', system='snes')
        self.assertFalse(rows)
        self.assertEqual(len(missing), 1)

    def test_crc_match_keeps_priority(self):
        rows, missing = self.match('Mega Man (USA)', 'Different title [A413EBC7]',
                                   crc='A413EBC7')
        self.assertFalse(missing)
        self.assertEqual(rows[0]['status'], 'CRC_MATCH')


if __name__ == '__main__':
    unittest.main()
