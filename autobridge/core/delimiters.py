"""
AutoBridge - Core Delimiter Protocol Extractor
ANSI X12 / ISO 9735 Standard Delimiter Discovery

In the ANSI X12 standard, delimiters are NOT hardcoded.
The first segment in any X12 stream is always the Interchange Control Header (ISA).
The ISA segment defines the delimiter rules for the entire transmission.
"""

from dataclasses import dataclass
from typing import Optional


class DelimiterError(ValueError):
    """Raised when the EDI stream does not conform to ANSI X12 header rules."""
    pass


@dataclass(frozen=True)
class X12Delimiters:
    element_separator: str          # Separates elements within a segment (e.g. '*')
    component_separator: str        # Sub-element separator in composite elements (e.g. ':', '>')
    segment_terminator: str         # Terminates each segment (e.g. '~', '\n', '\r\n')
    repetition_separator: Optional[str] = None  # X12 v4020+ repetition separator (ISA11)

    def __post_init__(self):
        if not self.element_separator:
            raise DelimiterError("Element separator cannot be empty.")
        if not self.component_separator:
            raise DelimiterError("Component separator cannot be empty.")
        if not self.segment_terminator:
            raise DelimiterError("Segment terminator cannot be empty.")
        
        # Verify delimiters are distinct
        if self.element_separator == self.segment_terminator:
            raise DelimiterError(
                f"Element separator and segment terminator collide: '{self.element_separator}'"
            )
        if self.element_separator == self.component_separator:
            raise DelimiterError(
                f"Element separator and component separator collide: '{self.element_separator}'"
            )


def extract_delimiters(edi_content: str) -> X12Delimiters:
    """
    Extracts delimiters dynamically from the initial ISA segment.
    
    The ISA header has an exact fixed-length structure:
      - Bytes 0-2:   'ISA'
      - Byte 3:      Element separator (traditionally '*')
      - Elements 1-15: Fixed widths separated by the element separator
      - Byte 104:    Component element separator (ISA16, traditionally ':', '>')
      - Byte 105+:   Segment terminator (traditionally '~', or newline)
    """
    # Strip leading byte order marks (BOM) or whitespace if present
    content = edi_content.lstrip('\ufeff \r\n\t')
    
    if len(content) < 106:
        raise DelimiterError(
            f"Content too short for valid ANSI X12 ISA header (expected >= 106 chars, got {len(content)})."
        )

    if not content.startswith("ISA"):
        raise DelimiterError(
            f"Invalid EDI stream: Missing 'ISA' header tag at start of transmission (found '{content[:3]}')."
        )

    element_sep = content[3]
    if element_sep in ('\r', '\n', ' '):
        raise DelimiterError(
            f"Invalid element separator: Whitespace or newline character '{repr(element_sep)}' at byte 3."
        )

    # Validate that ISA has exactly 1 tag + 16 elements = 17 parts
    parts = content[:105].split(element_sep)
    # parts[0] is 'ISA'
    # parts[1..15] are ISA01 to ISA15
    # parts[16] is ISA16 (1 char component separator)
    if len(parts) != 17:
        raise DelimiterError(
            f"Malformed ISA fixed header: expected 17 tokens ('ISA' + 16 elements) separated by '{element_sep}', found {len(parts)}. "
            "File does not conform to ANSI X12 fixed-width ISA standard."
        )

    # Component separator is at index 104 (ISA16)
    component_sep = content[104]
    if component_sep in ('\r', '\n', ' '):
        raise DelimiterError(
            f"Invalid component separator: Whitespace or newline '{repr(component_sep)}' at byte 104."
        )

    # Segment terminator starts at index 105
    # It might be 1 char (e.g. '~' or '\n') or 2 chars (e.g. '~\n' or '\r\n')
    term_char = content[105]
    
    # Check for two-character terminators (e.g. '\r\n' or '~' followed by newline)
    if term_char == '\r' and len(content) > 106 and content[106] == '\n':
        segment_term = '\r\n'
    elif term_char == '~':
        segment_term = '~'
    elif term_char == '^':
        segment_term = '^'
    elif term_char == '\n':
        segment_term = '\n'
    else:
        # Generic single character terminator
        segment_term = term_char

    # Repetition separator in ISA11 (X12 version 00402+)
    # parts[11] is ISA11 (1 char)
    repetition_sep = parts[11] if len(parts[11]) == 1 and parts[11] not in ('U', '') else None

    return X12Delimiters(
        element_separator=element_sep,
        component_separator=component_sep,
        segment_terminator=segment_term,
        repetition_separator=repetition_sep
    )
