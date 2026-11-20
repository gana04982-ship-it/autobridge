"""
AutoBridge - Precision Test Harness: Lexer & Delimiters
Validates ANSI X12 tokenization against edge cases and malformed inputs.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from autobridge.core.delimiters import extract_delimiters, DelimiterError, X12Delimiters
from autobridge.core.lexer import tokenize_x12, X12Segment, LexerError


class TestX12Delimiters(unittest.TestCase):

    def test_standard_delimiters(self):
        # 106 chars exact ISA header
        isa = (
            "ISA*00*          *00*          *ZZ*SUPPLIER       "
            "*01*FORDMOTOR      *261119*1400*U*00401*000000001*0*P*>~"
        )
        self.assertEqual(len(isa), 106)
        delims = extract_delimiters(isa)
        self.assertEqual(delims.element_separator, "*")
        self.assertEqual(delims.component_separator, ">")
        self.assertEqual(delims.segment_terminator, "~")

    def test_pipe_and_caret_delimiters(self):
        # Non-standard EDI with '|' elements, ':' component, '^' terminator
        isa = (
            "ISA|00|          |00|          |ZZ|SUPPLIER       "
            "|01|FORDMOTOR      |261119|1400|U|00401|000000001|0|P|:^"
        )
        self.assertEqual(len(isa), 106)
        delims = extract_delimiters(isa)
        self.assertEqual(delims.element_separator, "|")
        self.assertEqual(delims.component_separator, ":")
        self.assertEqual(delims.segment_terminator, "^")

    def test_short_isa_rejection(self):
        with self.assertRaises(DelimiterError) as ctx:
            extract_delimiters("ISA*00*SHORT*HEADER~")
        self.assertIn("too short", str(ctx.exception).lower())

    def test_missing_isa_tag_rejection(self):
        with self.assertRaises(DelimiterError) as ctx:
            extract_delimiters("XYZ*00*          *00*          *ZZ*SUPPLIER       *01*FORDMOTOR      *261119*1400*U*00401*000000001*0*P*>~")
        self.assertIn("missing 'isa' header", str(ctx.exception).lower())

    def test_delimiter_collision_rejection(self):
        # If element separator and component separator collide
        with self.assertRaises(DelimiterError):
            X12Delimiters(element_separator="*", component_separator="*", segment_terminator="~")


class TestX12Lexer(unittest.TestCase):

    def setUp(self):
        self.sample_edi = (
            "ISA*00*          *00*          *ZZ*SUPPLIER       *01*FORDMOTOR      *261119*1400*U*00401*000000001*0*P*>~\n"
            "GS*SH*SUPPLIER*FORDMOTOR*20261119*1400*1*X*004010~\n"
            "ST*856*0001~\n"
            "BSN*00*SHIP98765*20261119*1400~\n"
            "HL*1**S~\n"
            "SE*4*0001~\n"
            "GE*1*1~\n"
            "IEA*1*000000001~"
        )

    def test_tokenize_standard_stream(self):
        segments = tokenize_x12(self.sample_edi)
        self.assertEqual(len(segments), 8)
        
        tags = [s.tag for s in segments]
        self.assertEqual(tags, ["ISA", "GS", "ST", "BSN", "HL", "SE", "GE", "IEA"])

        # Test 1-based indexing on ST segment
        st = segments[2]
        self.assertEqual(st.tag, "ST")
        self.assertEqual(st.get(1), "856")
        self.assertEqual(st.get(2), "0001")
        self.assertEqual(st.get(3), "")  # Non-existent element returns default empty

        # Test empty element in HL segment (HL*1**S -> HL01=1, HL02='', HL03=S)
        hl = segments[4]
        self.assertEqual(hl.tag, "HL")
        self.assertEqual(hl.get(1), "1")
        self.assertEqual(hl.get(2), "")
        self.assertEqual(hl.get(3), "S")

    def test_single_line_continuous_stream(self):
        # Continuous raw stream without newlines
        continuous = (
            "ISA*00*          *00*          *ZZ*SUPPLIER       *01*FORDMOTOR      *261119*1400*U*00401*000000001*0*P*>~"
            "GS*SH*SUPPLIER*FORDMOTOR*20261119*1400*1*X*004010~"
            "ST*856*0001~"
            "SE*1*0001~"
            "GE*1*1~"
            "IEA*1*000000001~"
        )
        segments = tokenize_x12(continuous)
        self.assertEqual(len(segments), 6)
        self.assertEqual(segments[0].tag, "ISA")
        self.assertEqual(segments[-1].tag, "IEA")

    def test_composite_sub_elements(self):
        edi_with_composite = (
            "ISA*00*          *00*          *ZZ*SUPPLIER       *01*FORDMOTOR      *261119*1400*U*00401*000000001*0*P*>~\n"
            "ST*856*0001~\n"
            "MEA*PD*G*1450.50*LB>01~\n"
            "SE*2*0001~\n"
            "GE*1*1~\n"
            "IEA*1*000000001~"
        )
        segments = tokenize_x12(edi_with_composite)
        mea = segments[2]
        self.assertEqual(mea.tag, "MEA")
        self.assertEqual(mea.get(1), "PD")
        self.assertEqual(mea.get(2), "G")
        self.assertEqual(mea.get(3), "1450.50")
        self.assertEqual(mea.get(4), "LB>01")
        # Verify sub-elements split by '>'
        self.assertEqual(mea.sub_elements[4], ["LB", "01"])

    def test_empty_input_rejection(self):
        with self.assertRaises(LexerError):
            tokenize_x12("   \n\t  ")


if __name__ == "__main__":
    unittest.main()
