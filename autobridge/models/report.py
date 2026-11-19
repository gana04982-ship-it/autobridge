"""
AutoBridge - Diagnostic Audit Report Model
Produces structured, typed compliance reports with line numbers and fix guidance.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class RuleViolation:
    rule_id: str                # E.g. "FORD-001-MISSING-BOL", "AIAG-005-WEIGHT-BALANCE"
    severity: str               # "CRITICAL", "ERROR", "WARNING"
    line_number: int            # Line number in source EDI file
    segment_tag: str            # "REF", "TD1", "LIN", etc.
    message: str                # Plain-English dock explanation
    violating_value: str        # Raw value that triggered the violation
    expected_rule: str          # OEM Specification citation
    fix_recommendation: str     # Exact action required to prevent chargeback


@dataclass
class ShipmentSummary:
    shipment_id: str = ""
    carrier_scac: str = ""
    bill_of_lading: str = ""
    ship_to_code: str = ""
    ship_to_name: str = ""
    ship_from_code: str = ""
    ship_date: str = ""
    declared_pallets: int = 0
    actual_pallets_in_tree: int = 0
    declared_gross_weight: str = ""
    purchase_orders: List[str] = field(default_factory=list)
    part_numbers: List[str] = field(default_factory=list)
    total_parts_shipped: int = 0


@dataclass
class AuditReport:
    is_compliant: bool
    oem_profile: str            # E.g. "FORD-AIAG-B10" or "GM-1724"
    total_violations: int
    critical_errors: int
    warnings: int
    violations: List[RuleViolation]
    shipment_summary: ShipmentSummary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_compliant": self.is_compliant,
            "oem_profile": self.oem_profile,
            "total_violations": self.total_violations,
            "critical_errors": self.critical_errors,
            "warnings": self.warnings,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "severity": v.severity,
                    "line_number": v.line_number,
                    "segment": v.segment_tag,
                    "message": v.message,
                    "violating_value": v.violating_value,
                    "rule": v.expected_rule,
                    "fix": v.fix_recommendation
                }
                for v in self.violations
            ],
            "shipment_summary": {
                "shipment_id": self.shipment_summary.shipment_id,
                "carrier": self.shipment_summary.carrier_scac,
                "bill_of_lading": self.shipment_summary.bill_of_lading,
                "ship_to": self.shipment_summary.ship_to_code,
                "ship_from": self.shipment_summary.ship_from_code,
                "declared_pallets": self.shipment_summary.declared_pallets,
                "actual_pallets": self.shipment_summary.actual_pallets_in_tree,
                "purchase_orders": self.shipment_summary.purchase_orders,
                "part_numbers": self.shipment_summary.part_numbers,
                "total_parts_shipped": self.shipment_summary.total_parts_shipped
            }
        }
