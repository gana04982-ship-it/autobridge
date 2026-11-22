"""
Integration tests for AutoBridge Folder-Watcher Sidecar Daemon.
"""

import os
import shutil
import tempfile
import unittest

from autobridge.watcher import FolderWatcherDaemon


SAMPLE_DEFECTIVE = """ISA*00*          *00*          *ZZ*SUPPLIER       *ZZ*FORD           *261122*0915*U*00401*000000001*0*T*:~
GS*SH*SUPPLIER*FORD*20261122*0915*1*X*004010~
ST*856*0001~
BSN*00*ADV-10492*20261122*0915~
HL*1**S~
TD1*PLT90*2****G*1200*LB~
HL*2*1*O~
PRF*PO-1001~
HL*3*2*T~
HL*4*3*I~
LIN*1*BP*9L3Z-100-A~
SN1**50*EA~
SE*12*0001~
GE*1*1~
IEA*1*000000001~"""


class TestWatcherDaemon(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.in_dir = os.path.join(self.test_dir, "incoming")
        self.out_dir = os.path.join(self.test_dir, "ready")
        self.archive_dir = os.path.join(self.test_dir, "archive")
        self.quarantine_dir = os.path.join(self.test_dir, "quarantine")

        self.daemon = FolderWatcherDaemon(
            in_dir=self.in_dir,
            out_dir=self.out_dir,
            archive_dir=self.archive_dir,
            quarantine_dir=self.quarantine_dir,
            oem_profile="FORD-AIAG-B10"
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_process_valid_edi(self):
        sample_path = os.path.join(self.in_dir, "shipment_01.856")
        with open(sample_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_DEFECTIVE)

        processed = self.daemon.run_once()
        self.assertEqual(processed, 1)

        # In directory must be empty
        self.assertFalse(os.path.exists(sample_path))
        
        # Out directory must have repaired file
        out_file = os.path.join(self.out_dir, "shipment_01.856")
        self.assertTrue(os.path.exists(out_file))

        # Archive must have original copy
        orig_archive_files = os.listdir(os.path.join(self.archive_dir, "original"))
        self.assertEqual(len(orig_archive_files), 1)

    def test_quarantine_garbage(self):
        garbage_path = os.path.join(self.in_dir, "corrupt.txt")
        with open(garbage_path, "w", encoding="utf-8") as f:
            f.write("THIS IS NOT AN EDI FILE")

        processed = self.daemon.run_once()
        self.assertEqual(processed, 0)
        self.assertFalse(os.path.exists(garbage_path))
        
        # Check quarantine
        q_files = [f for f in os.listdir(self.quarantine_dir) if not f.endswith(".json")]
        self.assertEqual(len(q_files), 1)


if __name__ == "__main__":
    unittest.main()
