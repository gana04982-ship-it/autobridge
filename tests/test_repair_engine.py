"""
AutoBridge - Unit Tests for AutoRepairEngine
Validates 100% deterministic auto-repair of broken ANSI X12 856 EDI payloads.
"""

import unittest
from autobridge.engine import AutoBridgeEngine
from autobridge.repair import AutoRepairEngine


TRAP_EDI = (
    "ISA*00*          *00*          *ZZ*SUPPLIER       *01*FORDMOTOR      *261119*1400*U*00401*000000001*0*P*>~\n"
    "GS*SH*SUPPLIER*FORDMOTOR*20261119*1400*1*X*004010~\n"
    "ST*856*0001~\n"
    "BSN*00*SHIP99999*20261119*1400~\n"
    "DTM*011*20261119*1400~\n"
    "HL*1**S~\n"
    "MEA*PD*G*1500*LB~\n"
    "TD1*PLT90*2~\n"
    "TD5*B*02*FXFW*M~\n"
    "N1*ST*FORD DEARBORN TRUCK*92*00123~\n"
    "N1*SF*SUPPLIER DETROIT PLANT*92*99887~\n"
    "HL*2*1*O~\n"
    "PRF*PO-887766~\n"
    "HL*3*2*T~\n"
    "MAN*GM*1J000123456789012345~\n"
    "HL*4*3*P~\n"
    "MAN*GM*3S000123456789012345~\n"
    "HL*5*4*I~\n"
    "LIN**ZZ*W300-84920-AA~\n"
    "SN1**100*EA~\n"
    "SE*19*0001~\n"
    "GE*1*1~\n"
    "IEA*1*000000001~"
)


class TestAutoRepairEngine(unittest.TestCase):
    def setUp(self):
        self.engine = AutoBridgeEngine(oem_profile="FORD-AIAG-B10")
        self.repairer = AutoRepairEngine(oem_profile="FORD-AIAG-B10")

    def test_pre_repair_violations_detected(self):
        pre_report = self.engine.audit(TRAP_EDI)
        self.assertFalse(pre_report.is_compliant)
        self.assertEqual(pre_report.total_violations, 3)

    def test_deterministic_repair_eliminates_all_violations(self):
        rep = self.repairer.repair(TRAP_EDI)
        self.assertGreaterEqual(rep["total_fixes"], 3)
        self.assertIn("repaired_edi", rep)
        self.assertIn("repaired_segments", rep)

        # Post repair audit must pass with 0 errors
        post_report = self.engine.audit(rep["repaired_edi"])
        self.assertTrue(post_report.is_compliant)
        self.assertEqual(post_report.total_violations, 0)
        self.assertEqual(post_report.critical_errors, 0)

    def test_recalculated_se01_matches_exact_segment_depth(self):
        rep = self.repairer.repair(TRAP_EDI)
        repaired = rep["repaired_edi"]
        se_line = [line for line in repaired.split("~") if line.strip().startswith("SE*")][0]
        # With inserted REF*BM segment, count increases from 19 to 20
        self.assertIn("SE*20*", se_line)


if __name__ == "__main__":
    unittest.main()
