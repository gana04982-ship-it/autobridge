"""
AutoBridge - Precision Test Harness: HL Tree Graph Topology
Validates hierarchical tree construction and relationship integrity in X12 856.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from autobridge.core.lexer import tokenize_x12
from autobridge.core.envelope import validate_envelopes
from autobridge.core.hl_tree import build_hl_tree


class TestHLTreeBuilder(unittest.TestCase):

    def setUp(self):
        # Realistic Ford SO-TPI Hierarchical Structure
        # 1: Shipment (S)
        # 2: Order (O) -> child of 1
        # 3: Tare / Pallet (T) -> child of 2
        # 4: Pack / Box (P) -> child of 3
        # 5: Item / Part (I) -> child of 4
        self.sample_asn = (
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

    def test_clean_tree_construction(self):
        segments = tokenize_x12(self.sample_asn)
        envelope = validate_envelopes(segments)
        tx = envelope.groups[0].transaction_sets[0]
        
        tree = build_hl_tree(tx.segments)
        self.assertEqual(len(tree.violations), 0)
        self.assertEqual(len(tree.nodes), 5)

        # 1. Root Shipment check
        root = tree.get_shipment()
        self.assertIsNotNone(root)
        self.assertEqual(root.hl_id, 1)
        self.assertEqual(root.level_code, 'S')
        self.assertIsNone(root.parent)
        self.assertEqual(len(root.children), 1)

        # Check attached segments to Shipment (MEA, TD1, TD5, REF, N1*ST, N1*SF)
        shipment_tags = [s.tag for s in root.segments]
        self.assertIn("MEA", shipment_tags)
        self.assertIn("TD1", shipment_tags)
        self.assertIn("TD5", shipment_tags)
        self.assertIn("REF", shipment_tags)
        self.assertEqual(len(root.get_segments("N1")), 2)

        # 2. Order Node check
        order = root.children[0]
        self.assertEqual(order.hl_id, 2)
        self.assertEqual(order.level_code, 'O')
        self.assertEqual(order.parent_id, 1)
        self.assertEqual(order.get_segment("PRF").get(1), "PO-554433")

        # 3. Pallet (Tare) Node check
        pallet = order.children[0]
        self.assertEqual(pallet.hl_id, 3)
        self.assertEqual(pallet.level_code, 'T')
        self.assertEqual(pallet.get_segment("MAN").get(2), "1J000123456789012345")

        # 4. Box (Pack) Node check
        box = pallet.children[0]
        self.assertEqual(box.hl_id, 4)
        self.assertEqual(box.level_code, 'P')

        # 5. Item Node check
        item = box.children[0]
        self.assertEqual(item.hl_id, 5)
        self.assertEqual(item.level_code, 'I')
        self.assertEqual(item.get_segment("LIN").get(2), "BP")
        self.assertEqual(item.get_segment("LIN").get(3), "W300-84920-AA")
        self.assertEqual(item.get_segment("SN1").get(2), "100")

        # Verify recursive descendant collection
        all_items = root.find_descendants_by_level('I')
        self.assertEqual(len(all_items), 1)
        self.assertEqual(all_items[0].hl_id, 5)

    def test_orphan_parent_detection(self):
        # Corrupt parent reference: HL*3*99*T (parent 99 does not exist)
        corrupted = self.sample_asn.replace("HL*3*2*T~", "HL*3*99*T~")
        segments = tokenize_x12(corrupted)
        envelope = validate_envelopes(segments)
        tx = envelope.groups[0].transaction_sets[0]

        tree = build_hl_tree(tx.segments)
        self.assertGreater(len(tree.violations), 0)
        codes = [v.code for v in tree.violations]
        self.assertIn("HL_ORPHAN_PARENT", codes)

    def test_duplicate_hl_id_detection(self):
        # Corrupt: two segments with HL01=2
        corrupted = self.sample_asn.replace("HL*3*2*T~", "HL*2*2*T~")
        segments = tokenize_x12(corrupted)
        envelope = validate_envelopes(segments)
        tx = envelope.groups[0].transaction_sets[0]

        tree = build_hl_tree(tx.segments)
        codes = [v.code for v in tree.violations]
        self.assertIn("HL_DUPLICATE_ID", codes)

    def test_invalid_level_code(self):
        # Corrupt level code from 'S' to 'Z'
        corrupted = self.sample_asn.replace("HL*1**S~", "HL*1**Z~")
        segments = tokenize_x12(corrupted)
        envelope = validate_envelopes(segments)
        tx = envelope.groups[0].transaction_sets[0]

        tree = build_hl_tree(tx.segments)
        codes = [v.code for v in tree.violations]
        self.assertIn("HL_INVALID_LEVEL_CODE", codes)


if __name__ == "__main__":
    unittest.main()
