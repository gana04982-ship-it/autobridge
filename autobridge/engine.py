"""
AutoBridge - Unified Pre-Flight Verification Engine
Public API for scanning and certifying EDI 856 Advance Ship Notices.
"""

from typing import Union, Dict, Any
from autobridge.core.delimiters import extract_delimiters
from autobridge.core.lexer import tokenize_x12
from autobridge.core.envelope import validate_envelopes
from autobridge.core.hl_tree import build_hl_tree
from autobridge.rules.ford_aiag import audit_ford_aiag
from autobridge.models.report import AuditReport


class AutoBridgeEngine:
    """
    Precision verification engine for automotive supply chain EDI transmissions.
    """

    def __init__(self, oem_profile: str = "FORD-AIAG-B10"):
        self.oem_profile = oem_profile.upper()

    def audit(self, edi_content: str) -> AuditReport:
        """
        Runs comprehensive multi-tier pre-flight verification:
          Tier 1: Delimiter & Lexer syntax
          Tier 2: Envelope counts (ISA/IEA, GS/GE, ST/SE)
          Tier 3: Hierarchical Level (HL) tree graph topology
          Tier 4: OEM Semantic dock rules (Ford / AIAG B-10)
        """
        # 1. Lexical Tokenization
        delimiters = extract_delimiters(edi_content)
        segments = tokenize_x12(edi_content, delimiters=delimiters)

        # 2. Envelope Integrity
        envelope = validate_envelopes(segments)

        # 3. Extract primary transaction set (first ST 856)
        if not envelope.groups or not envelope.groups[0].transaction_sets:
            raise ValueError("No valid transaction sets found in EDI transmission.")

        tx = envelope.groups[0].transaction_sets[0]

        # 4. HL Graph Tree Construction
        tree = build_hl_tree(tx.segments)

        # 5. OEM Semantic Rules
        if "FORD" in self.oem_profile or "AIAG" in self.oem_profile:
            report = audit_ford_aiag(envelope, tree)
        else:
            # Default to Ford AIAG
            report = audit_ford_aiag(envelope, tree)

        return report
