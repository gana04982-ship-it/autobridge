"""
Unit tests for AutoBridge Core Safety, Dual-Write & Fail-Open Watchdog.
"""

import os
import shutil
import tempfile
import unittest

from autobridge.core.safety import (
    atomic_write_file, 
    DualWriteArchiver, 
    FailOpenWatchdog, 
    QuarantineManager
)


class TestSafetyCore(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_atomic_write(self):
        target = os.path.join(self.test_dir, "test.856")
        content = "ISA*00*...~ST*856*0001~SE*10*0001~"
        atomic_write_file(target, content)
        
        self.assertTrue(os.path.exists(target))
        with open(target, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), content)

    def test_dual_write_archiver(self):
        archiver = DualWriteArchiver(os.path.join(self.test_dir, "archive"))
        orig = "ST*856*0001~HL*1**S~SE*3*0001~"
        repaired = "ST*856*0001~HL*1**S~REF*BM*123~SE*4*0001~"
        changes = [{"tag": "REF", "action": "Injected BOL"}]

        res = archiver.archive("manifest_101.856", orig, repaired, changes)
        
        self.assertTrue(os.path.exists(res["original_archive"]))
        self.assertTrue(os.path.exists(res["diff_archive"]))
        self.assertEqual(len(res["sha256"]), 64)

    def test_fail_open_watchdog_on_crash(self):
        watchdog = FailOpenWatchdog(os.path.join(self.test_dir, "logs"))
        input_file = os.path.join(self.test_dir, "broken.856")
        raw_text = "CORRUPTED_RAW_CONTENT"
        with open(input_file, "w", encoding="utf-8") as f:
            f.write(raw_text)

        out_file = os.path.join(self.test_dir, "ready", "broken.856")

        def buggy_repair(content):
            raise RuntimeError("Simulated Parser Crash!")

        # Execute safe dispatch - MUST NOT CRASH
        success, status, result = watchdog.execute_safe_dispatch(input_file, out_file, buggy_repair)
        
        # Verify fail-open behavior:
        self.assertFalse(success)
        self.assertIn("FAIL_OPEN_ENGAGED", status)
        self.assertIsNone(result)
        
        # Destination MUST have original file so truck departs
        self.assertTrue(os.path.exists(out_file))
        with open(out_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), raw_text)
            
        # Warning stamp and crash log must exist
        self.assertTrue(os.path.exists(f"{out_file}.bypass.warning"))
        self.assertTrue(os.path.exists(watchdog.crash_log))

    def test_quarantine_manager(self):
        qm = QuarantineManager(os.path.join(self.test_dir, "quarantine"))
        bad_file = os.path.join(self.test_dir, "empty.txt")
        with open(bad_file, "w") as f:
            f.write("")

        q_path = qm.quarantine(bad_file, "ZERO_BYTE_FILE")
        self.assertTrue(os.path.exists(q_path))
        self.assertTrue(os.path.exists(f"{q_path}.diagnosis.json"))


if __name__ == "__main__":
    unittest.main()
