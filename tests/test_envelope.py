"""
AutoBridge - Precision Test Harness: Envelope Integrity
Validates ANSI X12 structural envelopes (ISA/IEA, GS/GE, ST/SE).
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from autobridge.core.lexer import tokenize_x12
from autobridge.core.envelope import validate_envelopes


class TestEnvelopeValidator(unittest.TestCase):

    def setUp(self):
        # 100% valid EDI stream with exact segment counts
        # ST through SE has exactly 4 segments: ST, BSN, HL, SE -> SE01 must be 4
        self.clean_edi = (
            "ISA*00*          *00*          *ZZ*SUPPLIER       *01*FORDMOTOR      *261119*1400*U*00401*000000001*0*P*>~\n"
            "GS*SH*SUPPLIER*FORDMOTOR*20261119*1400*1*X*004010~\n"
            "ST*856*0001~\n"
            "BSN*00*SHIP98765*20261119*1400~\n"
            "HL*1**S~\n"
            "SE*4*0001~\n"
            "GE*1*1~\n"
            "IEA*1*000000001~"
        )

    def test_clean_envelope_zero_violations(self):
        segments = tokenize_x12(self.clean_edi)
        envelope = validate_envelopes(segments)
        self.assertEqual(len(envelope.violations), 0)
        self.assertEqual(len(envelope.groups), 1)
        group = envelope.groups[0]
        self.assertEqual(len(group.violations), 0)
        self.assertEqual(len(group.transaction_sets), 1)
        tx = group.transaction_sets[0]
        self.assertEqual(len(tx.violations), 0)
        self.assertEqual(tx.control_number, "0001")

    def test_se01_segment_count_mismatch(self):
        # Corrupt SE01 from 4 to 99
        corrupted = self.clean_edi.replace("SE*4*0001~", "SE*99*0001~")
        segments = tokenize_x12(corrupted)
        envelope = validate_envelopes(segments)
        tx = envelope.groups[0].transaction_sets[0]
        
        self.assertEqual(len(tx.violations), 1)
        v = tx.violations[0]
        self.assertEqual(v.code, "ENV_SE01_COUNT_MISMATCH")
        self.assertEqual(v.expected, "4")
        self.assertEqual(v.found, "99")
        self.assertIn("Update SE01 from 99 to 4", v.fix_recommendation)

    def test_st02_se02_control_mismatch(self):
        # ST02 is 0001, SE02 is 9999
        corrupted = self.clean_edi.replace("SE*4*0001~", "SE*4*9999~")
        segments = tokenize_x12(corrupted)
        envelope = validate_envelopes(segments)
        tx = envelope.groups[0].transaction_sets[0]
        
        self.assertEqual(len(tx.violations), 1)
        v = tx.violations[0]
        self.assertEqual(v.code, "ENV_SE02_CONTROL_MISMATCH")
        self.assertEqual(v.expected, "0001")
        self.assertEqual(v.found, "9999")

    def test_gs06_ge02_control_mismatch(self):
        # GS06 is 1, GE02 is 888
        corrupted = self.clean_edi.replace("GE*1*1~", "GE*1*888~")
        segments = tokenize_x12(corrupted)
        envelope = validate_envelopes(segments)
        group = envelope.groups[0]
        
        self.assertEqual(len(group.violations), 1)
        v = group.violations[0]
        self.assertEqual(v.code, "ENV_GE_CONTROL_MISMATCH")

    def test_isa13_iea02_control_mismatch(self):
        # ISA13 is 000000001, IEA02 is 999999999
        corrupted = self.clean_edi.replace("IEA*1*000000001~", "IEA*1*999999999~")
        segments = tokenize_x12(corrupted)
        envelope = validate_envelopes(segments)
        
        self.assertEqual(len(envelope.violations), 1)
        v = envelope.violations[0]
        self.assertEqual(v.code, "ENV_IEA02_CONTROL_MISMATCH")
        self.assertEqual(v.expected, "000000001")
        self.assertEqual(v.found, "999999999")

    def test_ge01_transaction_count_mismatch(self):
        # Declares 5 transaction sets in GE01, but only 1 exists
        corrupted = self.clean_edi.replace("GE*1*1~", "GE*5*1~")
        segments = tokenize_x12(corrupted)
        envelope = validate_envelopes(segments)
        group = envelope.groups[0]
        
        self.assertEqual(len(group.violations), 1)
        v = group.violations[0]
        self.assertEqual(v.code, "ENV_GE01_COUNT_MISMATCH")
        self.assertEqual(v.expected, "1")
        self.assertEqual(v.found, "5")


if __name__ == "__main__":
    unittest.main()
