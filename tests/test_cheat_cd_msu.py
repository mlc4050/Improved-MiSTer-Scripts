import contextlib
import io
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

api = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                        'check_mister_cheats_v10.py'))


class CdAndMsuTests(unittest.TestCase):
    def test_rondo_and_cotton_collection_aliases(self):
        examples = (
            ('Akumajou Dracula X - Chi no Rondo (Japan) (FABT, FACT)',
             'Akumajou Dracula X - Chi no Rondo (SCD)(Jpn)'),
            ('Fantastic Night Dreams - Cotton (USA)',
             'Cotton - Fantastic Night Dreams (SCD)(USA)'),
        )
        for game_title, cheat_title in examples:
            with self.subTest(game=game_title):
                game = dict(system='turbografx16cd', stem=game_title,
                            path='TGFX16-CD/game.cue', crc='', stripped='')
                cheat = dict(system='turbografx16cd', stem=cheat_title,
                             path='TGFX16-CD/cheat.zip', crc='', issue='')
                rows, missing = api['compare']([cheat], [game])
                self.assertFalse(missing)
                self.assertTrue(rows[0]['name_match'])
                self.assertFalse(rows[0]['crc_match'])
                game['stem'] += ' [Hack]'
                self.assertTrue(api['compare']([cheat], [game])[1])
        key = api['match_title_key']
        self.assertNotEqual(key('turbografx16cd', 'Fantastic Night Dreams - Cotton (Japan)'),
                            key('turbografx16cd', 'Cotton - Fantastic Night Dreams (USA)'))

    def test_bonk_media_tags_and_cd_regions(self):
        title = "Bonk III - Bonk's Big Adventure"
        cheat = dict(system='turbografx16cd', stem=title + ' (SCD)(USA)',
                     path='TGFX16-CD/Bonk.zip', crc='', issue='')
        game = dict(system='turbografx16cd', stem=title + ' (USA)',
                    path='TGFX16-CD/Bonk.cue', crc='', stripped='')
        rows, missing = api['compare']([cheat], [game])
        self.assertFalse(missing)
        self.assertTrue(rows[0]['name_match'])
        self.assertFalse(rows[0]['crc_match'])
        key = api['match_title_key']
        self.assertEqual(key('psx', 'Example (CD, SCD)(Jpn)'),
                         key('psx', 'Example (Japan)'))
        self.assertEqual(key('megacd', 'Example (Euro)'),
                         key('megacd', 'Example (Europe)'))
        for different in (title + ' (Japan)', title + ' (USA) (Rev 1)',
                          title + ' (USA) [Hack]'):
            self.assertNotEqual(key('turbografx16cd', cheat['stem']),
                                key('turbografx16cd', different))
        self.assertNotEqual(key('nes', 'Example (CD)(USA)'),
                            key('nes', 'Example (USA)'))

    def test_all_fifteen_cheat_folders_in_menu(self):
        folders = ('AtariLynx', 'GAMEBOY', 'GBA', 'Jaguar', 'MegaCD',
                   'MegaDrive', 'N64', 'NES', 'PSX', 'SGB', 'SMS', 'SNES',
                   'TGFX16', 'TGFX16-CD', 'VirtualBoy')
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            root = Path(tmp)
            for tree in ('cheats', 'games'):
                for folder in folders:
                    (root / tree / folder).mkdir(parents=True)
            with patch('builtins.input', return_value='a'), contextlib.redirect_stdout(io.StringIO()):
                selected = api['select_consoles'](root / 'cheats', root / 'games')
            self.assertEqual(len(selected), 15)
            self.assertIn('psx', selected)
            self.assertIn('sgb', selected)
            self.assertEqual(api['system_key']('AtariLynx'), api['system_key']('Lynx'))
            for folder, extension in (('PSX', '.chd'), ('Jaguar', '.j64'),
                                      ('AtariLynx', '.lnx'), ('VirtualBoy', '.vb')):
                (root / 'games' / folder / ('Example' + extension)).write_bytes(b'rom')
            errors, skipped = [], []
            games = api['inventory_games'](root / 'games', selected, errors, skipped)
            self.assertEqual(len(games), 4)
            self.assertFalse(errors)
            self.assertFalse(skipped)

    def test_cd_menu_inventory_and_name_matching(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            root = Path(tmp)
            games, cheats = root / 'games', root / 'cheats'
            for base, folders in ((games, ('SegaCD', 'PCE-CD')),
                                  (cheats, ('MegaCD', 'TGFX16-CD'))):
                for folder in folders:
                    (base / folder).mkdir(parents=True)
            (games / 'SegaCD' / 'Example.cue').write_text('FILE "track.bin" BINARY')
            (games / 'SegaCD' / 'track.bin').write_bytes(b'track')
            (games / 'PCE-CD' / 'Disc 1.chd').write_bytes(b'image')
            (games / 'PCE-CD' / 'Example.m3u').write_text('Disc 1.chd\n')
            with patch('builtins.input', return_value='a'), contextlib.redirect_stdout(io.StringIO()):
                selected = api['select_consoles'](cheats, games)
            self.assertEqual(selected, {'megacd', 'turbografx16cd'})
            errors, skipped = [], []
            inventory = api['inventory_games'](games, selected, errors, skipped, True)
            self.assertFalse(errors)
            self.assertFalse(skipped)
            self.assertEqual(len(inventory), 2)
            self.assertTrue(all(not g['crc'] for g in inventory))
            cheat = dict(system='megacd', stem='Example [12345678]',
                         crc='12345678', path='MegaCD/Example.zip', issue='')
            rows, missing = api['compare']([cheat], inventory)
            self.assertEqual(len(missing), 1)
            self.assertEqual(rows[0]['status'], 'EXACT_NAME_MATCH')
            self.assertIn('CD image CRC/game ID is not checked', rows[0]['note'])

    def test_msu_folders_files_assets_and_palettes_ignored(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            root = Path(tmp)
            for name in ('MSU-1', 'MSU1', 'Soundtracks [MSU-1]'):
                folder = root / 'SNES' / name
                folder.mkdir(parents=True)
                (folder / 'Game.sfc').write_bytes(b'rom')
            folder = root / 'SNES'
            for name in ('Game [MSU-1].sfc', 'audio.pcm', 'audio.msu', 'color.PAL', 'Normal.sfc'):
                (folder / name).write_bytes(b'rom')
            errors, skipped = [], []
            games = api['inventory_games'](root, {'snes'}, errors, skipped)
            self.assertFalse(errors)
            self.assertFalse(skipped)
            self.assertEqual([g['stem'] for g in games], ['Normal'])


if __name__ == '__main__':
    unittest.main()
