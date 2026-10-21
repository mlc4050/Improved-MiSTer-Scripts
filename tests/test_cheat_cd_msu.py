import contextlib
import io
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

api = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                        'check_mister_cheats_v8.py'))


class CdAndMsuTests(unittest.TestCase):
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
