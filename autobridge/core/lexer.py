"""
AutoBridge - Core ANSI X12 Lexer & Tokenizer
Transforms raw byte/character streams into structured X12 Segments.
"""

from dataclasses import dataclass, field
from typing import List, Generator
from autobridge.core.delimiters import X12Delimiters, extract_delimiters


@dataclass
class X12Segment:
    tag: str                    # E.g. "ST", "BSN", "HL", "LIN", "MEA"
    elements: List[str]         # 1-indexed elements: elements[0] is tag, elements[1] is 01, elements[2] is 02...
    raw: str                    # Exact raw segment string
    line_number: int            # 1-based line index in the source file
    sub_elements: List[List[str]] = field(default_factory=list) # Split composite elements

    def get(self, index: int, default: str = "") -> str:
        """
        Safely retrieves an element by 1-based X12 index (e.g. segment.get(1) for BSN01).
        """
        if 0 <= index < len(self.elements):
            return self.elements[index]
        return default

    def __repr__(self) -> str:
        return f"<X12Segment [{self.tag}] Line:{self.line_number} Elements:{len(self.elements) - 1}>"


class LexerError(ValueError):
    """Raised on critical syntax errors during X12 tokenization."""
    def __init__(self, message: str, line_number: int = 1):
        super().__init__(f"Line {line_number}: {message}")
        self.line_number = line_number


def tokenize_x12(content: str, delimiters: X12Delimiters = None) -> List[X12Segment]:
    """
    Parses an EDI string into a list of X12Segment objects.
    Maintains exact 1-based indexing for all data elements (e.g. ST01 is elements[1]).
    """
    if not content or not content.strip():
        raise LexerError("Empty or blank EDI stream provided.", line_number=1)

    clean_content = content.lstrip('\ufeff \r\n\t')
    if delimiters is None:
        delimiters = extract_delimiters(clean_content)

    term = delimiters.segment_terminator
    elem_sep = delimiters.element_separator
    comp_sep = delimiters.component_separator

    segments: List[X12Segment] = []
    
    # Split content by the segment terminator while tracking line numbers
    # We must be careful: some files have newlines after '~', some are continuous single-line streams.
    current_line = 1
    raw_segments = clean_content.split(term)

    for idx, raw_seg in enumerate(raw_segments):
        # Count newlines in raw_seg to keep line counter accurate
        lines_in_seg = raw_seg.count('\n')
        
        # Clean segment text (strip leading/trailing newlines between terminators)
        stripped = raw_seg.strip(' \r\n\t')
        
        # Trailing empty segment after last terminator is expected
        if not stripped:
            current_line += lines_in_seg
            continue

        # Split elements by element_separator
        raw_elements = stripped.split(elem_sep)
        tag = raw_elements[0].strip()

        if not tag:
            raise LexerError("Found empty segment tag before delimiter.", line_number=current_line)

        # Validate tag characters (standard X12 tags are 2-3 alphanumeric characters)
        if not (2 <= len(tag) <= 3 and tag.isalnum()):
            # Allow common envelope/transaction tags
            raise LexerError(
                f"Invalid segment identifier '{tag}' (must be 2-3 alphanumeric characters).",
                line_number=current_line
            )

        # Build composite sub-elements if component separator is present
        sub_elements = []
        for elem in raw_elements:
            if comp_sep and comp_sep in elem:
                sub_elements.append(elem.split(comp_sep))
            else:
                sub_elements.append([elem])

        segments.append(
            X12Segment(
                tag=tag,
                elements=raw_elements,
                raw=stripped,
                line_number=current_line,
                sub_elements=sub_elements
            )
        )

        current_line += lines_in_seg

    if not segments:
        raise LexerError("No valid X12 segments found in stream.", line_number=1)

    return segments
