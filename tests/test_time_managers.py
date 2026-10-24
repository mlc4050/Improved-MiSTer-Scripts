import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tz = load('timezone_manager_v1')
rtc = load('rtc_manager_v1')


class TimeManagerTests(unittest.TestCase):
    def test_zone_inventory_rejects_metadata_and_duplicate_trees(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as tmp:
            root = Path(tmp)
            for name in ('America/Test', 'UTC', 'posix/America/Test', 'right/UTC'):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'TZif' + b'fixture')
            (root / 'zone.tab').write_text('metadata')
            self.assertEqual(set(tz.available_zones(root)), {'America/Test', 'UTC'})

    def test_zone_write_validation_idempotence_and_atomic_failure(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as tmp:
            root = Path(tmp)
            source, target = root / 'source', root / 'timezone'
            source.write_bytes(b'TZifnew')
            target.write_bytes(b'TZifold')
            zones = {'America/Test': source}
            with self.assertRaises(ValueError):
                tz.write_zone('../../other', zones, target)
            with patch.object(tz.os, 'replace', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    tz.write_zone('America/Test', zones, target)
            self.assertEqual(target.read_bytes(), b'TZifold')
            self.assertFalse(list(root.glob('.timezone-*')))
            self.assertTrue(tz.write_zone('America/Test', zones, target))
            self.assertFalse(tz.write_zone('America/Test', zones, target))

    def test_search_and_alias_status(self):
        self.assertEqual(tz.matching_zones('new york', {'America/New_York': None}), ['America/New_York'])

    def test_rtc_absent_never_writes(self):
        with patch.object(rtc, 'rtc_devices', return_value=[]), patch.object(rtc, 'run') as run:
            with self.assertRaises(RuntimeError):
                rtc.save_rtc()
            run.assert_not_called()

    def test_ntp_failure_does_not_write_rtc(self):
        with patch.object(rtc.shutil, 'which', return_value='/bin/tool'), patch.object(rtc, 'run', side_effect=RuntimeError('offline')) as run:
            with self.assertRaises(RuntimeError):
                rtc.sync_system('0.pool.ntp.org')
            self.assertEqual(run.call_args.args[0][0], 'ntpdate')
            self.assertEqual(run.call_count, 1)

    def test_rtc_write_uses_utc_without_adjtime(self):
        with patch.object(rtc, 'rtc_devices', return_value=['/dev/rtc0']), patch.object(rtc.shutil, 'which', return_value='/bin/hwclock'), patch.object(rtc, 'run') as run:
            rtc.save_rtc()
            self.assertEqual(run.call_args.args[0], ['hwclock', '--systohc', '--utc', '--noadjfile'])


if __name__ == '__main__':
    unittest.main()
