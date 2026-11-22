"""
Unit tests for AutoBridge Forensic Historical Chargeback Auditor.
"""

import os
import shutil
import tempfile
import unittest

from autobridge.forensic import ForensicAuditor


SAMPLE_DEFECTIVE_856 = """ISA*00*          *00*          *ZZ*SUPPLIER       *ZZ*FORD           *261122*0915*U*00401*000000001*0*T*:~
GS*SH*SUPPLIER*FORD*20261122*0915*1*X*004010~
ST*856*0001~
BSN*00*BOL-98401*20261122*0915~
HL*1**S~
TD1*PLT90*4****G*1250*LB~
TD5*B*2*EXPD*M~
DTM*011*202611221000~
DTM*017*202611220800~
HL*2*1*O~
PRF*PO-98421~
HL*3*2*T~
HL*4*99*I~
LIN*1*VP*9L3Z-16000-A~
SN1**100*EA~
SE*14*0001~
GE*1*1~
IEA*1*000000001~"""


class TestForensicAuditor(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.sample_file = os.path.join(self.test_dir, "historical_sample.856")
        with open(self.sample_file, "w", encoding="utf-8") as f:
            f.write(SAMPLE_DEFECTIVE_856)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_audit_batch(self):
        auditor = ForensicAuditor(oem_profile="FORD-AIAG-B10")
        result = auditor.audit_batch([self.sample_file])

        self.assertEqual(result["total_files_audited"], 1)
        self.assertEqual(result["defective_files"], 1)
        self.assertGreater(result["total_estimated_fine_exposure_usd"], 0)
        self.assertEqual(result["autobridge_resolution_rate_pct"], 100.0)

        # Test executive markdown report generation
        md = auditor.generate_executive_markdown_report(result, company_name="Henniges Automotive")
        self.assertIn("Henniges Automotive", md)
        self.assertIn("avoidable chargeback", md.lower())
        self.assertIn("FINANCIAL ROI COMPARISON", md)


if __name__ == "__main__":
    unittest.main()
