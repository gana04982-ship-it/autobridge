"""
AutoBridge - Core Envelope Integrity Validator
Validates ANSI X12 structural envelopes:
  - ISA / IEA (Interchange Control Envelope)
  - GS / GE   (Functional Group Envelope)
  - ST / SE   (Transaction Set Envelope)
"""

from dataclasses import dataclass
from typing import List, Optional
from autobridge.core.lexer import X12Segment


@dataclass
class EnvelopeViolation:
    code: str                   # E.g. "ENV_SE01_COUNT_MISMATCH"
    severity: str               # "CRITICAL", "ERROR", "WARNING"
    line_number: int            # Line number where error was detected
    segment_tag: str            # "SE", "IEA", "GE", etc.
    message: str                # Human-readable explanation
    expected: str
    found: str
    fix_recommendation: str     # Actionable guidance to eliminate the violation


@dataclass
class TransactionSet:
    st_segment: X12Segment
    se_segment: Optional[X12Segment]
    segments: List[X12Segment]
    control_number: str
    set_type: str               # E.g. "856"
    violations: List[EnvelopeViolation]


@dataclass
class FunctionalGroup:
    gs_segment: X12Segment
    ge_segment: Optional[X12Segment]
    transaction_sets: List[TransactionSet]
    group_control_number: str
    functional_code: str        # E.g. "SH"
    version: str                # E.g. "004010"
    violations: List[EnvelopeViolation]


@dataclass
class InterchangeEnvelope:
    isa_segment: X12Segment
    iea_segment: Optional[X12Segment]
    groups: List[FunctionalGroup]
    control_number: str
    violations: List[EnvelopeViolation]


def validate_envelopes(segments: List[X12Segment]) -> InterchangeEnvelope:
    """
    Validates structural envelope integrity across all nesting levels:
      ISA -> GS -> ST ... SE -> GE -> IEA
    Checks control numbers, segment counts, and group tallies.
    """
    violations: List[EnvelopeViolation] = []
    
    if not segments:
        raise ValueError("Cannot validate envelopes of empty segment list.")

    # 1. Verify ISA exists at start
    isa_seg = segments[0]
    if isa_seg.tag != "ISA":
        violations.append(
            EnvelopeViolation(
                code="ENV_MISSING_ISA",
                severity="CRITICAL",
                line_number=isa_seg.line_number,
                segment_tag=isa_seg.tag,
                message=f"Transmission must begin with 'ISA' segment. Found '{isa_seg.tag}'.",
                expected="ISA",
                found=isa_seg.tag,
                fix_recommendation="Ensure the file begins with an ANSI X12 ISA header."
            )
        )

    # 2. Verify IEA exists at end
    iea_seg = segments[-1] if segments[-1].tag == "IEA" else None
    if iea_seg is None:
        violations.append(
            EnvelopeViolation(
                code="ENV_MISSING_IEA",
                severity="CRITICAL",
                line_number=segments[-1].line_number,
                segment_tag=segments[-1].tag,
                message=f"Transmission must terminate with 'IEA' segment. Found '{segments[-1].tag}'.",
                expected="IEA",
                found=segments[-1].tag,
                fix_recommendation="Ensure the file concludes with an ANSI X12 IEA trailer."
            )
        )

    isa_control = isa_seg.get(13) if isa_seg.tag == "ISA" else ""

    # Parse nested groups and transaction sets
    groups: List[FunctionalGroup] = []
    current_group: Optional[FunctionalGroup] = None
    current_tx: Optional[TransactionSet] = None

    for seg in segments[1:-1] if iea_seg else segments[1:]:
        if seg.tag == "GS":
            if current_group is not None:
                # Unclosed prior group
                current_group.violations.append(
                    EnvelopeViolation(
                        code="ENV_UNCLOSED_GS",
                        severity="CRITICAL",
                        line_number=seg.line_number,
                        segment_tag="GS",
                        message=f"New functional group 'GS' opened before prior group '{current_group.group_control_number}' was closed with 'GE'.",
                        expected="GE",
                        found="GS",
                        fix_recommendation="Close each GS group with a matching GE trailer before opening another."
                    )
                )
            current_group = FunctionalGroup(
                gs_segment=seg,
                ge_segment=None,
                transaction_sets=[],
                group_control_number=seg.get(6),
                functional_code=seg.get(1),
                version=seg.get(8),
                violations=[]
            )
            groups.append(current_group)

        elif seg.tag == "GE":
            if current_group is None:
                violations.append(
                    EnvelopeViolation(
                        code="ENV_ORPHAN_GE",
                        severity="CRITICAL",
                        line_number=seg.line_number,
                        segment_tag="GE",
                        message="Encountered 'GE' trailer without a preceding 'GS' header.",
                        expected="GS",
                        found="GE",
                        fix_recommendation="Verify group envelope structure."
                    )
                )
            else:
                current_group.ge_segment = seg
                # Validate GE02 matches GS06
                ge_ctrl = seg.get(2)
                if ge_ctrl != current_group.group_control_number:
                    current_group.violations.append(
                        EnvelopeViolation(
                            code="ENV_GE_CONTROL_MISMATCH",
                            severity="CRITICAL",
                            line_number=seg.line_number,
                            segment_tag="GE",
                            message=f"Functional group control number mismatch: GS06='{current_group.group_control_number}' vs GE02='{ge_ctrl}'.",
                            expected=current_group.group_control_number,
                            found=ge_ctrl,
                            fix_recommendation="Synchronize GS06 and GE02 control numbers."
                        )
                    )
                # Validate GE01 matches count of included transaction sets
                expected_st_count = len(current_group.transaction_sets)
                try:
                    found_st_count = int(seg.get(1, "0"))
                    if found_st_count != expected_st_count:
                        current_group.violations.append(
                            EnvelopeViolation(
                                code="ENV_GE01_COUNT_MISMATCH",
                                severity="CRITICAL",
                                line_number=seg.line_number,
                                segment_tag="GE",
                                message=f"Group transaction set count mismatch: GE01 declares {found_st_count}, but found {expected_st_count} ST transaction(s).",
                                expected=str(expected_st_count),
                                found=str(found_st_count),
                                fix_recommendation=f"Update GE01 to {expected_st_count}."
                            )
                        )
                except ValueError:
                    current_group.violations.append(
                        EnvelopeViolation(
                            code="ENV_GE01_INVALID_NUMBER",
                            severity="CRITICAL",
                            line_number=seg.line_number,
                            segment_tag="GE",
                            message=f"GE01 value '{seg.get(1)}' is not a valid integer.",
                            expected="Integer",
                            found=seg.get(1),
                            fix_recommendation="Ensure GE01 is numeric."
                        )
                    )
                current_group = None

        elif seg.tag == "ST":
            if current_group is None:
                violations.append(
                    EnvelopeViolation(
                        code="ENV_ST_OUTSIDE_GS",
                        severity="CRITICAL",
                        line_number=seg.line_number,
                        segment_tag="ST",
                        message="Encountered 'ST' transaction outside of an active functional group 'GS'.",
                        expected="GS",
                        found="ST",
                        fix_recommendation="Wrap all ST transaction sets inside a GS/GE group."
                    )
                )
            current_tx = TransactionSet(
                st_segment=seg,
                se_segment=None,
                segments=[seg],
                control_number=seg.get(2),
                set_type=seg.get(1),
                violations=[]
            )
            if current_group:
                current_group.transaction_sets.append(current_tx)

        elif seg.tag == "SE":
            if current_tx is None:
                violations.append(
                    EnvelopeViolation(
                        code="ENV_ORPHAN_SE",
                        severity="CRITICAL",
                        line_number=seg.line_number,
                        segment_tag="SE",
                        message="Encountered 'SE' trailer without an open 'ST' transaction set.",
                        expected="ST",
                        found="SE",
                        fix_recommendation="Verify ST/SE transaction pairing."
                    )
                )
            else:
                current_tx.se_segment = seg
                current_tx.segments.append(seg)
                
                # Check 1: SE02 control number matches ST02
                se_ctrl = seg.get(2)
                if se_ctrl != current_tx.control_number:
                    current_tx.violations.append(
                        EnvelopeViolation(
                            code="ENV_SE02_CONTROL_MISMATCH",
                            severity="CRITICAL",
                            line_number=seg.line_number,
                            segment_tag="SE",
                            message=f"Transaction control number mismatch: ST02='{current_tx.control_number}' vs SE02='{se_ctrl}'.",
                            expected=current_tx.control_number,
                            found=se_ctrl,
                            fix_recommendation="Ensure SE02 matches ST02."
                        )
                    )
                
                # Check 2: SE01 segment count matches exact included segments (inclusive of ST and SE)
                actual_count = len(current_tx.segments)
                try:
                    declared_count = int(seg.get(1, "0"))
                    if declared_count != actual_count:
                        current_tx.violations.append(
                            EnvelopeViolation(
                                code="ENV_SE01_COUNT_MISMATCH",
                                severity="CRITICAL",
                                line_number=seg.line_number,
                                segment_tag="SE",
                                message=f"Segment count mismatch: SE01 declares {declared_count} segments, but actual segment count between ST and SE is {actual_count}.",
                                expected=str(actual_count),
                                found=str(declared_count),
                                fix_recommendation=f"Update SE01 from {declared_count} to {actual_count}."
                            )
                        )
                except ValueError:
                    current_tx.violations.append(
                        EnvelopeViolation(
                            code="ENV_SE01_INVALID_NUMBER",
                            severity="CRITICAL",
                            line_number=seg.line_number,
                            segment_tag="SE",
                            message=f"SE01 value '{seg.get(1)}' is not a valid integer count.",
                            expected="Integer",
                            found=seg.get(1),
                            fix_recommendation="Ensure SE01 is numeric."
                        )
                    )
                current_tx = None

        else:
            # Normal inner segment
            if current_tx is not None:
                current_tx.segments.append(seg)
            else:
                violations.append(
                    EnvelopeViolation(
                        code="ENV_SEGMENT_OUTSIDE_TRANSACTION",
                        severity="ERROR",
                        line_number=seg.line_number,
                        segment_tag=seg.tag,
                        message=f"Segment '{seg.tag}' found floating outside an active ST/SE transaction set.",
                        expected="Inside ST/SE",
                        found=seg.tag,
                        fix_recommendation="Place all business data segments between ST and SE."
                    )
                )

    # 3. Final IEA verification against ISA
    if iea_seg:
        iea_ctrl = iea_seg.get(2)
        if isa_control and iea_ctrl != isa_control:
            violations.append(
                EnvelopeViolation(
                    code="ENV_IEA02_CONTROL_MISMATCH",
                    severity="CRITICAL",
                    line_number=iea_seg.line_number,
                    segment_tag="IEA",
                    message=f"Interchange control number mismatch: ISA13='{isa_control}' vs IEA02='{iea_ctrl}'.",
                    expected=isa_control,
                    found=iea_ctrl,
                    fix_recommendation="Ensure IEA02 matches ISA13 exactly."
                )
            )
        try:
            declared_groups = int(iea_seg.get(1, "0"))
            actual_groups = len(groups)
            if declared_groups != actual_groups:
                violations.append(
                    EnvelopeViolation(
                        code="ENV_IEA01_GROUP_COUNT_MISMATCH",
                        severity="CRITICAL",
                        line_number=iea_seg.line_number,
                        segment_tag="IEA",
                        message=f"Functional group count mismatch: IEA01 declares {declared_groups}, but found {actual_groups} GS group(s).",
                        expected=str(actual_groups),
                        found=str(declared_groups),
                        fix_recommendation=f"Update IEA01 to {actual_groups}."
                    )
                )
        except ValueError:
            violations.append(
                EnvelopeViolation(
                    code="ENV_IEA01_INVALID_NUMBER",
                    severity="CRITICAL",
                    line_number=iea_seg.line_number,
                    segment_tag="IEA",
                    message=f"IEA01 value '{iea_seg.get(1)}' is not a valid integer.",
                    expected="Integer",
                    found=iea_seg.get(1),
                    fix_recommendation="Ensure IEA01 is numeric."
                )
            )

    return InterchangeEnvelope(
        isa_segment=isa_seg,
        iea_segment=iea_seg,
        groups=groups,
        control_number=isa_control,
        violations=violations
    )
