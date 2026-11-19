"""
AutoBridge - Brutal Engine Test Suite: Real-World OEM Chargeback Traps
Simulates real factory EDI failures that trigger $5,000 to $15,000 OEM fines.
"""

import unittest
from autobridge.engine import AutoBridgeEngine


class TestAutoBridgeBrutal(unittest.TestCase):

    def setUp(self):
        self.engine = AutoBridgeEngine(oem_profile="FORD-AIAG-B10")
        
        # 100% Clean Production ASN (Ford Spec: 1 Pallet, 1 Box, 100 parts)
        self.clean_asn = (
            "ISA*00*          *00*          *ZZ*SUPPLIER       *01*FORDMOTOR      *261119*1400*U*00401*000000001*0*P*>~\n"
            "GS*SH*SUPPLIER*FORDMOTOR*20261119*1400*1*X*004010~\n"
            "ST*856*0001~\n"
            "BSN*00*SHIP12345*20261119*1400~\n"
            "DTM*011*20261119*1400~\n"
            "HL*1**S~\n"
            "MEA*PD*G*1500*LB~\n"
            "TD1*PLT90*1~\n"
            "TD5*B*02*FXFW*M~\n"
            "REF*BM*BOL-987654~\n"
            "N1*ST*FORD DEARBORN TRUCK*92*00123~\n"
            "N1*SF*SUPPLIER DETROIT PLANT*92*99887~\n"
            "HL*2*1*O~\n"
            "PRF*PO-554433~\n"
            "HL*3*2*T~\n"
            "MAN*GM*1J000123456789012345~\n"
            "HL*4*3*P~\n"
            "MAN*GM*3S000123456789012345~\n"
            "HL*5*4*I~\n"
            "LIN**BP*W300-84920-AA~\n"
            "SN1**100*EA~\n"
            "SE*20*0001~\n"
            "GE*1*1~\n"
            "IEA*1*000000001~"
        )

    def test_clean_production_manifest_certified(self):
        report = self.engine.audit(self.clean_asn)
        self.assertTrue(report.is_compliant)
        self.assertEqual(report.critical_errors, 0)
        self.assertEqual(report.total_violations, 0)
        self.assertEqual(report.shipment_summary.shipment_id, "SHIP12345")
        self.assertEqual(report.shipment_summary.bill_of_lading, "BOL-987654")
        self.assertEqual(report.shipment_summary.carrier_scac, "FXFW")
        self.assertEqual(report.shipment_summary.declared_pallets, 1)
        self.assertEqual(report.shipment_summary.actual_pallets_in_tree, 1)
        self.assertEqual(report.shipment_summary.total_parts_shipped, 100)
        self.assertIn("W300-84920-AA", report.shipment_summary.part_numbers)
        self.assertIn("PO-554433", report.shipment_summary.purchase_orders)

    def test_pallet_tally_mismatch_detected(self):
        # Corrupt: TD1 says 2 pallets, but tree only has 1 pallet
        corrupted = self.clean_asn.replace("TD1*PLT90*1~", "TD1*PLT90*2~")
        report = self.engine.audit(corrupted)
        self.assertFalse(report.is_compliant)
        rule_ids = [v.rule_id for v in report.violations]
        self.assertIn("FORD-008-PALLET-COUNT-MISMATCH", rule_ids)

    def test_missing_bill_of_lading_detected(self):
        # Delete REF*BM line (and adjust SE count)
        corrupted = self.clean_asn.replace("REF*BM*BOL-987654~\n", "").replace("SE*20*0001~", "SE*19*0001~")
        report = self.engine.audit(corrupted)
        self.assertFalse(report.is_compliant)
        rule_ids = [v.rule_id for v in report.violations]
        self.assertIn("FORD-003-MISSING-BOL", rule_ids)

    def test_duplicate_pallet_barcode_detected(self):
        # Create a 2-pallet ASN with identical pallet barcodes
        two_pallet_asn = (
            "ISA*00*          *00*          *ZZ*SUPPLIER       *01*FORDMOTOR      *261119*1400*U*00401*000000001*0*P*>~\n"
            "GS*SH*SUPPLIER*FORDMOTOR*20261119*1400*1*X*004010~\n"
            "ST*856*0001~\n"
            "BSN*00*SHIP12345*20261119*1400~\n"
            "DTM*011*20261119*1400~\n"
            "HL*1**S~\n"
            "MEA*PD*G*3000*LB~\n"
            "TD1*PLT90*2~\n"
            "TD5*B*02*FXFW*M~\n"
            "REF*BM*BOL-987654~\n"
            "N1*ST*FORD DEARBORN TRUCK*92*00123~\n"
            "N1*SF*SUPPLIER DETROIT PLANT*92*99887~\n"
            "HL*2*1*O~\n"
            "PRF*PO-554433~\n"
            "HL*3*2*T~\n"
            "MAN*GM*SAME-BARCODE-12345~\n"
            "HL*4*3*I~\n"
            "LIN**BP*W300-84920-AA~\n"
            "SN1**50*EA~\n"
            "HL*5*2*T~\n"
            "MAN*GM*SAME-BARCODE-12345~\n"  # Duplicate!
            "HL*6*5*I~\n"
            "LIN**BP*W300-84920-AA~\n"
            "SN1**50*EA~\n"
            "SE*22*0001~\n"
            "GE*1*1~\n"
            "IEA*1*000000001~"
        )
        report = self.engine.audit(two_pallet_asn)
        self.assertFalse(report.is_compliant)
        rule_ids = [v.rule_id for v in report.violations]
        self.assertIn("FORD-015-DUPLICATE-PALLET-SERIAL", rule_ids)

    def test_invalid_buyer_part_qualifier_detected(self):
        # Corrupt: LIN**ZZ*W300... (ZZ instead of mandatory BP)
        corrupted = self.clean_asn.replace("LIN**BP*", "LIN**ZZ*")
        report = self.engine.audit(corrupted)
        self.assertFalse(report.is_compliant)
        rule_ids = [v.rule_id for v in report.violations]
        self.assertIn("FORD-018-INVALID-PART-QUALIFIER", rule_ids)

    def test_se_segment_count_drift_detected(self):
        # Corrupt: SE01 says 25, but actual count is 20
        corrupted = self.clean_asn.replace("SE*20*0001~", "SE*25*0001~")
        report = self.engine.audit(corrupted)
        self.assertFalse(report.is_compliant)
        rule_ids = [v.rule_id for v in report.violations]
        self.assertIn("ENV_SE01_COUNT_MISMATCH", rule_ids)

    def test_zero_shipped_quantity_detected(self):
        # Corrupt: SN1**0*EA~
        corrupted = self.clean_asn.replace("SN1**100*EA~", "SN1**0*EA~")
        report = self.engine.audit(corrupted)
        self.assertFalse(report.is_compliant)
        rule_ids = [v.rule_id for v in report.violations]
        self.assertIn("FORD-021-ZERO-QUANTITY", rule_ids)


if __name__ == "__main__":
    unittest.main()
