"""
AutoBridge - Ford Motor Company & AIAG B-10 Specification Rule Engine
Implements deterministic semantic validation checks required by Ford automated docks.
"""

from typing import List, Set
from autobridge.core.envelope import InterchangeEnvelope, TransactionSet
from autobridge.core.hl_tree import HLTree, HLNode
from autobridge.models.report import RuleViolation, ShipmentSummary, AuditReport


def audit_ford_aiag(envelope: InterchangeEnvelope, tree: HLTree) -> AuditReport:
    """
    Executes Ford AIAG B-10 semantic rule verification across the envelope and HL tree.
    Returns a comprehensive AuditReport with exact line numbers and remediation steps.
    """
    violations: List[RuleViolation] = []
    summary = ShipmentSummary()

    # 1. Bubble up envelope violations
    for ev in envelope.violations:
        violations.append(
            RuleViolation(
                rule_id=ev.code,
                severity=ev.severity,
                line_number=ev.line_number,
                segment_tag=ev.segment_tag,
                message=ev.message,
                violating_value=ev.found,
                expected_rule=f"ANSI X12 Envelope Standard ({ev.expected})",
                fix_recommendation=ev.fix_recommendation
            )
        )

    for group in envelope.groups:
        for gv in group.violations:
            violations.append(
                RuleViolation(
                    rule_id=gv.code,
                    severity=gv.severity,
                    line_number=gv.line_number,
                    segment_tag=gv.segment_tag,
                    message=gv.message,
                    violating_value=gv.found,
                    expected_rule="ANSI X12 Group Standard",
                    fix_recommendation=gv.fix_recommendation
                )
            )
        for tx in group.transaction_sets:
            for tv in tx.violations:
                violations.append(
                    RuleViolation(
                        rule_id=tv.code,
                        severity=tv.severity,
                        line_number=tv.line_number,
                        segment_tag=tv.segment_tag,
                        message=tv.message,
                        violating_value=tv.found,
                        expected_rule="ANSI X12 Transaction Set Standard",
                        fix_recommendation=tv.fix_recommendation
                    )
                )

    # 2. Bubble up HL tree graph violations
    for hv in tree.violations:
        violations.append(
            RuleViolation(
                rule_id=hv.code,
                severity=hv.severity,
                line_number=hv.line_number,
                segment_tag="HL",
                message=hv.message,
                violating_value=hv.hl_id,
                expected_rule="AIAG Hierarchical Topology",
                fix_recommendation=hv.fix_recommendation
            )
        )

    shipment_node = tree.get_shipment()
    if shipment_node is None:
        violations.append(
            RuleViolation(
                rule_id="FORD-000-NO-SHIPMENT-ROOT",
                severity="CRITICAL",
                line_number=1,
                segment_tag="HL",
                message="Advance Ship Notice is missing root Shipment level (HL*...*S).",
                violating_value="None",
                expected_rule="Ford AIAG: HL03='S' must be root node",
                fix_recommendation="Define root HL segment with level code 'S'."
            )
        )
        return AuditReport(
            is_compliant=False,
            oem_profile="FORD-AIAG-B10",
            total_violations=len(violations),
            critical_errors=len([v for v in violations if v.severity == "CRITICAL"]),
            warnings=len([v for v in violations if v.severity == "WARNING"]),
            violations=violations,
            shipment_summary=summary
        )

    # 3. Audit Root Shipment Level Segments
    # -------------------------------------------------------------
    # BSN Segment (Beginning Segment for Ship Notice)
    bsn = shipment_node.get_segment("BSN")
    # If not on HL node, check prior segments in ST block
    if not bsn:
        for seg in tree.nodes[shipment_node.hl_id].segments:
            if seg.tag == "BSN":
                bsn = seg
                break
    if not bsn:
        # Search anywhere in transaction set
        for tx in envelope.groups[0].transaction_sets:
            for s in tx.segments:
                if s.tag == "BSN":
                    bsn = s
                    break

    if not bsn:
        violations.append(
            RuleViolation(
                rule_id="FORD-001-MISSING-BSN",
                severity="CRITICAL",
                line_number=shipment_node.hl_segment.line_number,
                segment_tag="BSN",
                message="Mandatory BSN (Beginning Segment for Ship Notice) is missing.",
                violating_value="Missing",
                expected_rule="Ford AIAG: BSN segment required immediately after ST",
                fix_recommendation="Add BSN segment with valid purpose code (BSN01='00') and shipment ID (BSN02)."
            )
        )
    else:
        summary.shipment_id = bsn.get(2)
        if not summary.shipment_id:
            violations.append(
                RuleViolation(
                    rule_id="FORD-002-EMPTY-SHIPMENT-ID",
                    severity="CRITICAL",
                    line_number=bsn.line_number,
                    segment_tag="BSN",
                    message="BSN02 Shipment Identification Number (Packing Slip / Manifest ID) cannot be empty.",
                    violating_value="",
                    expected_rule="Ford AIAG: BSN02 mandatory shipment ID (max 30 chars)",
                    fix_recommendation="Populate BSN02 with the internal packing slip number."
                )
            )

    # Bill of Lading (REF*BM)
    ref_bm = None
    for ref in shipment_node.get_segments("REF"):
        if ref.get(1) == "BM":
            ref_bm = ref
            break
    if not ref_bm:
        violations.append(
            RuleViolation(
                rule_id="FORD-003-MISSING-BOL",
                severity="CRITICAL",
                line_number=shipment_node.hl_segment.line_number,
                segment_tag="REF",
                message="Missing mandatory Bill of Lading number (REF*BM) at Shipment level.",
                violating_value="Missing",
                expected_rule="Ford AIAG B-10: REF*BM mandatory for dock receiving",
                fix_recommendation="Add REF*BM segment with Bill of Lading number under HL*...*S."
            )
        )
    else:
        summary.bill_of_lading = ref_bm.get(2)
        if not summary.bill_of_lading:
            violations.append(
                RuleViolation(
                    rule_id="FORD-004-EMPTY-BOL",
                    severity="CRITICAL",
                    line_number=ref_bm.line_number,
                    segment_tag="REF",
                    message="REF*BM segment has empty Bill of Lading value in REF02.",
                    violating_value="",
                    expected_rule="Ford AIAG: REF02 must contain carrier Bill of Lading",
                    fix_recommendation="Provide valid BOL number in REF02."
                )
            )

    # Carrier & SCAC Code (TD5)
    td5 = shipment_node.get_segment("TD5")
    if not td5:
        violations.append(
            RuleViolation(
                rule_id="FORD-005-MISSING-CARRIER",
                severity="CRITICAL",
                line_number=shipment_node.hl_segment.line_number,
                segment_tag="TD5",
                message="Missing carrier routing segment TD5 at Shipment level.",
                violating_value="Missing",
                expected_rule="Ford AIAG: TD5 mandatory with valid carrier SCAC code",
                fix_recommendation="Add TD5 segment (e.g. TD5*B*02*FXFW*M~)."
            )
        )
    else:
        summary.carrier_scac = td5.get(3).upper()
        if not (2 <= len(summary.carrier_scac) <= 4 and summary.carrier_scac.isalpha()):
            violations.append(
                RuleViolation(
                    rule_id="FORD-006-INVALID-SCAC",
                    severity="ERROR",
                    line_number=td5.line_number,
                    segment_tag="TD5",
                    message=f"Carrier SCAC code '{summary.carrier_scac}' in TD503 is invalid (must be 2-4 uppercase letters).",
                    violating_value=summary.carrier_scac,
                    expected_rule="Standard Carrier Alpha Code (SCAC) 2-4 letters",
                    fix_recommendation="Ensure TD503 contains a valid registered carrier SCAC (e.g. FXFW, CNWY, UPSN)."
                )
            )

    # Packaging & Pallet Declaration (TD1)
    td1 = shipment_node.get_segment("TD1")
    if td1:
        try:
            summary.declared_pallets = int(td1.get(2, "0"))
        except ValueError:
            violations.append(
                RuleViolation(
                    rule_id="FORD-007-INVALID-TD1-COUNT",
                    severity="ERROR",
                    line_number=td1.line_number,
                    segment_tag="TD1",
                    message=f"Declared packaging quantity '{td1.get(2)}' in TD102 is not a valid integer.",
                    violating_value=td1.get(2),
                    expected_rule="Ford AIAG: TD102 must be an integer count of packaging units",
                    fix_recommendation="Correct TD102 to an integer."
                )
            )

    # Cross-Check: Declared Pallets vs Pallets in Tree
    actual_pallets = len(tree.get_all_pallets())
    summary.actual_pallets_in_tree = actual_pallets
    if td1 and summary.declared_pallets > 0 and actual_pallets > 0:
        if summary.declared_pallets != actual_pallets:
            violations.append(
                RuleViolation(
                    rule_id="FORD-008-PALLET-COUNT-MISMATCH",
                    severity="CRITICAL",
                    line_number=td1.line_number,
                    segment_tag="TD1",
                    message=(
                        f"Packaging tally mismatch: TD102 declares {summary.declared_pallets} pallet(s), "
                        f"but HL tree contains {actual_pallets} Tare (T) level pallet node(s). "
                        "This will cause immediate dock barcode scanner rejection at Ford."
                    ),
                    violating_value=f"Declared:{summary.declared_pallets} vs Actual:{actual_pallets}",
                    expected_rule="Ford AIAG: Declared lading count must equal Tare HL nodes",
                    fix_recommendation=f"Update TD102 from {summary.declared_pallets} to {actual_pallets}."
                )
            )

    # Gross Weight (MEA)
    mea_g = None
    for mea in shipment_node.get_segments("MEA"):
        if mea.get(2) in ("G", "WT"):
            mea_g = mea
            break
    if not mea_g:
        violations.append(
            RuleViolation(
                rule_id="FORD-009-MISSING-GROSS-WEIGHT",
                severity="ERROR",
                line_number=shipment_node.hl_segment.line_number,
                segment_tag="MEA",
                message="Missing gross weight measurement segment MEA*PD*G at Shipment level.",
                violating_value="Missing",
                expected_rule="Ford AIAG: Gross weight MEA*PD*G mandatory",
                fix_recommendation="Add MEA segment with gross weight in pounds (LB) or kilograms (KG)."
            )
        )
    else:
        summary.declared_gross_weight = f"{mea_g.get(3)} {mea_g.get(4)}"

    # Ship-To Location (N1*ST)
    n1_st = None
    for n1 in shipment_node.get_segments("N1"):
        if n1.get(1) == "ST":
            n1_st = n1
            break
    if not n1_st:
        violations.append(
            RuleViolation(
                rule_id="FORD-010-MISSING-SHIP-TO",
                severity="CRITICAL",
                line_number=shipment_node.hl_segment.line_number,
                segment_tag="N1",
                message="Missing mandatory Ship-To location segment (N1*ST).",
                violating_value="Missing",
                expected_rule="Ford AIAG: N1*ST mandatory with customer plant code",
                fix_recommendation="Add N1*ST segment with Ford plant code in N104."
            )
        )
    else:
        summary.ship_to_code = n1_st.get(4)
        summary.ship_to_name = n1_st.get(2)

    # 4. Audit Order Level (HL*O)
    # -------------------------------------------------------------
    order_nodes = tree.get_all_orders()
    if not order_nodes:
        violations.append(
            RuleViolation(
                rule_id="FORD-011-NO-ORDER-NODES",
                severity="CRITICAL",
                line_number=shipment_node.hl_segment.line_number,
                segment_tag="HL",
                message="Advance Ship Notice contains zero Order level nodes (HL*...*O).",
                violating_value="0 Orders",
                expected_rule="Ford AIAG: At least one Order level required",
                fix_recommendation="Include Order level HL segment with PRF purchase order details."
            )
        )
    for ord_node in order_nodes:
        prf = ord_node.get_segment("PRF")
        if not prf or not prf.get(1):
            violations.append(
                RuleViolation(
                    rule_id="FORD-012-MISSING-PURCHASE-ORDER",
                    severity="CRITICAL",
                    line_number=ord_node.hl_segment.line_number,
                    segment_tag="PRF",
                    message="Order level node is missing customer Purchase Order number in PRF01.",
                    violating_value="Missing",
                    expected_rule="Ford AIAG: PRF01 mandatory customer PO number",
                    fix_recommendation="Populate PRF01 with Ford purchase order number."
                )
            )
        else:
            summary.purchase_orders.append(prf.get(1))

    # 5. Audit Tare Level (HL*T - Pallet Barcode Uniqueness)
    # -------------------------------------------------------------
    seen_pallet_serials: Set[str] = set()
    for pal_node in tree.get_all_pallets():
        man = pal_node.get_segment("MAN")
        if not man:
            violations.append(
                RuleViolation(
                    rule_id="FORD-013-MISSING-PALLET-SERIAL",
                    severity="CRITICAL",
                    line_number=pal_node.hl_segment.line_number,
                    segment_tag="MAN",
                    message="Tare pallet node is missing MAN segment (pallet license plate barcode ID).",
                    violating_value="Missing",
                    expected_rule="Ford AIAG: MAN*GM or MAN*UC mandatory with 2D barcode ID",
                    fix_recommendation="Add MAN*GM segment with unique pallet serial number."
                )
            )
        else:
            serial = man.get(2)
            if not serial:
                violations.append(
                    RuleViolation(
                        rule_id="FORD-014-EMPTY-PALLET-SERIAL",
                        severity="CRITICAL",
                        line_number=man.line_number,
                        segment_tag="MAN",
                        message="Pallet MAN segment has empty serial number in MAN02.",
                        violating_value="",
                        expected_rule="Ford AIAG: MAN02 must contain unique serial identifier",
                        fix_recommendation="Ensure MAN02 contains the 2D DataMatrix pallet barcode number."
                    )
                )
            elif serial in seen_pallet_serials:
                violations.append(
                    RuleViolation(
                        rule_id="FORD-015-DUPLICATE-PALLET-SERIAL",
                        severity="CRITICAL",
                        line_number=man.line_number,
                        segment_tag="MAN",
                        message=f"Duplicate pallet serial number '{serial}' detected. Each pallet must have a unique barcode.",
                        violating_value=serial,
                        expected_rule="AIAG Barcode Standard: Serial numbers must be unique per shipment",
                        fix_recommendation="Generate unique sequential serial numbers for each pallet."
                    )
                )
            else:
                seen_pallet_serials.add(serial)

    # 6. Audit Item Level (HL*I - Buyer Part Number & Quantities)
    # -------------------------------------------------------------
    item_nodes = tree.get_all_items()
    if not item_nodes:
        violations.append(
            RuleViolation(
                rule_id="FORD-016-NO-ITEM-NODES",
                severity="CRITICAL",
                line_number=shipment_node.hl_segment.line_number,
                segment_tag="HL",
                message="Advance Ship Notice contains zero Item level nodes (HL*...*I).",
                violating_value="0 Items",
                expected_rule="Ford AIAG: Manifest must contain at least one Item level",
                fix_recommendation="Include Item level nodes detailing shipped parts."
            )
        )

    for itm_node in item_nodes:
        lin = itm_node.get_segment("LIN")
        if not lin:
            violations.append(
                RuleViolation(
                    rule_id="FORD-017-MISSING-LIN-PART",
                    severity="CRITICAL",
                    line_number=itm_node.hl_segment.line_number,
                    segment_tag="LIN",
                    message="Item level node is missing LIN segment (Item Part Identification).",
                    violating_value="Missing",
                    expected_rule="Ford AIAG: LIN segment mandatory for parts identification",
                    fix_recommendation="Add LIN segment with buyer part number (LIN**BP*part_number~)."
                )
            )
        else:
            # Check LIN02 qualifier must be 'BP' (Buyer Part Number)
            qual = lin.get(2)
            part_num = lin.get(3)
            if qual != "BP":
                violations.append(
                    RuleViolation(
                        rule_id="FORD-018-INVALID-PART-QUALIFIER",
                        severity="CRITICAL",
                        line_number=lin.line_number,
                        segment_tag="LIN",
                        message=f"LIN02 qualifier must be 'BP' (Buyer's Part Number). Found '{qual}'.",
                        violating_value=qual,
                        expected_rule="Ford AIAG: LIN02 must equal 'BP'",
                        fix_recommendation="Set LIN02 qualifier to 'BP'."
                    )
                )
            if not part_num:
                violations.append(
                    RuleViolation(
                        rule_id="FORD-019-EMPTY-PART-NUMBER",
                        severity="CRITICAL",
                        line_number=lin.line_number,
                        segment_tag="LIN",
                        message="LIN03 Buyer Part Number cannot be empty.",
                        violating_value="",
                        expected_rule="Ford AIAG: LIN03 must contain Ford engineering part number",
                        fix_recommendation="Provide valid Ford part number in LIN03."
                    )
                )
            else:
                summary.part_numbers.append(part_num)

        # Quantity segment (SN1)
        sn1 = itm_node.get_segment("SN1")
        if not sn1:
            violations.append(
                RuleViolation(
                    rule_id="FORD-020-MISSING-SN1-QUANTITY",
                    severity="CRITICAL",
                    line_number=itm_node.hl_segment.line_number,
                    segment_tag="SN1",
                    message="Item level node is missing SN1 segment (Item Detail Shipment Quantity).",
                    violating_value="Missing",
                    expected_rule="Ford AIAG: SN1 segment mandatory with shipped quantity",
                    fix_recommendation="Add SN1 segment with quantity (SN1**qty*unit~)."
                )
            )
        else:
            try:
                qty = int(sn1.get(2, "0"))
                if qty <= 0:
                    violations.append(
                        RuleViolation(
                            rule_id="FORD-021-ZERO-QUANTITY",
                            severity="CRITICAL",
                            line_number=sn1.line_number,
                            segment_tag="SN1",
                            message=f"Shipped item quantity in SN102 must be greater than zero. Found {qty}.",
                            violating_value=str(qty),
                            expected_rule="Ford AIAG: SN102 > 0",
                            fix_recommendation="Ensure shipped quantity is positive."
                        )
                    )
                else:
                    summary.total_parts_shipped += qty
            except ValueError:
                violations.append(
                    RuleViolation(
                        rule_id="FORD-022-INVALID-QUANTITY-NUMBER",
                        severity="CRITICAL",
                        line_number=sn1.line_number,
                        segment_tag="SN1",
                        message=f"SN102 quantity value '{sn1.get(2)}' is not a valid integer.",
                        violating_value=sn1.get(2),
                        expected_rule="Ford AIAG: SN102 must be an integer count",
                        fix_recommendation="Set SN102 to a valid integer."
                    )
                )

    # 7. Final Compliance Determination
    critical_count = len([v for v in violations if v.severity == "CRITICAL"])
    error_count = len([v for v in violations if v.severity == "ERROR"])
    warning_count = len([v for v in violations if v.severity == "WARNING"])
    is_compliant = (critical_count == 0 and error_count == 0)

    return AuditReport(
        is_compliant=is_compliant,
        oem_profile="FORD-AIAG-B10",
        total_violations=len(violations),
        critical_errors=critical_count,
        warnings=warning_count,
        violations=violations,
        shipment_summary=summary
    )
