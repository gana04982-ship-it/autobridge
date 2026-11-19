"""
AutoBridge - Command-Line Interface (CLI)
Instant terminal pre-flight scanner for automotive EDI 856 Advance Ship Notices.
"""

import sys
import os
import json
import argparse
from autobridge.engine import AutoBridgeEngine
from autobridge.models.report import AuditReport


# ANSI Terminal Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def render_terminal_report(report: AuditReport, filename: str):
    print("\n" + "=" * 78)
    print(f"{BOLD}{CYAN}    🚀 AUTOBRIDGE PRE-FLIGHT EDI INSPECTOR — DOCK CERTIFICATION{RESET}")
    print("=" * 78)
    print(f"  {BOLD}Target File:{RESET}      {filename}")
    print(f"  {BOLD}OEM Rule Profile:{RESET} {report.oem_profile}")
    
    s = report.shipment_summary
    print(f"  {BOLD}Shipment ID:{RESET}      {s.shipment_id or 'UNKNOWN'}")
    print(f"  {BOLD}Carrier SCAC:{RESET}     {s.carrier_scac or 'UNKNOWN'} | {BOLD}BOL:{RESET} {s.bill_of_lading or 'UNKNOWN'}")
    print(f"  {BOLD}Ship-To Plant:{RESET}    {s.ship_to_code} ({s.ship_to_name})")
    print(f"  {BOLD}Pallet Count:{RESET}     Declared: {s.declared_pallets} | In Tree: {s.actual_pallets_in_tree}")
    print(f"  {BOLD}Parts Shipped:{RESET}    {s.total_parts_shipped} units across {len(s.part_numbers)} part number(s)")
    print("-" * 78)

    if report.is_compliant:
        print(f"\n{BOLD}{GREEN}  ✅ STATUS: 100% COMPLIANT — CERTIFIED SAFE TO SHIP{RESET}")
        print(f"  {GREEN}No OEM chargeback violations detected. Ready for dock receiving.{RESET}\n")
    else:
        print(f"\n{BOLD}{RED}  🛑 STATUS: DOCK REJECTION RISK — {report.critical_errors} CRITICAL VIOLATION(S){RESET}")
        print(f"  {RED}Transmitting this file will trigger an automated OEM chargeback fine.{RESET}\n")

        print(f"{BOLD}DETAILED VIOLATION AUDIT:{RESET}")
        print("-" * 78)
        for idx, v in enumerate(report.violations, 1):
            sev_color = RED if v.severity == "CRITICAL" else YELLOW
            print(f"{BOLD}{idx}. [{v.rule_id}]{RESET} Line {v.line_number} in segment {BOLD}{v.segment_tag}{RESET}")
            print(f"   {sev_color}Severity:{RESET} {v.severity}")
            print(f"   {BOLD}Dock Impact:{RESET} {v.message}")
            print(f"   {DIM}Violating Value:{RESET} '{v.violating_value}'")
            print(f"   {DIM}Specification Rule:{RESET} {v.expected_rule}")
            print(f"   {CYAN}👉 Remediation Action:{RESET} {v.fix_recommendation}\n")

    print("=" * 78 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="AutoBridge: Precision pre-flight validator for automotive EDI 856 Advance Ship Notices."
    )
    parser.add_argument("file", help="Path to raw EDI file (.edi, .x12, .txt)")
    parser.add_argument("--oem", default="FORD-AIAG-B10", help="OEM profile ruleset (default: FORD-AIAG-B10)")
    parser.add_argument("--json", action="store_true", help="Output audit report as JSON")

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"{RED}Error: File not found at '{args.file}'{RESET}", file=sys.stderr)
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    engine = AutoBridgeEngine(oem_profile=args.oem)
    try:
        report = engine.audit(content)
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            render_terminal_report(report, os.path.basename(args.file))
        
        sys.exit(0 if report.is_compliant else 2)

    except Exception as e:
        print(f"{RED}AutoBridge Syntax Error: {e}{RESET}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
