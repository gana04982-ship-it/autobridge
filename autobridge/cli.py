"""
AutoBridge - Command-Line Interface (CLI)
Instant terminal pre-flight scanner & deterministic auto-repair engine
for automotive EDI 856 Advance Ship Notices (AIAG B-10 & GM 1724).
"""

import sys
import os
import json
import argparse
import hashlib

# Ensure parent directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from autobridge.engine import AutoBridgeEngine
from autobridge.repair import AutoRepairEngine
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


def run_audit(file_path: str, oem: str, json_output: bool):
    if not os.path.exists(file_path):
        print(f"{RED}Error: File not found at '{file_path}'{RESET}", file=sys.stderr)
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    engine = AutoBridgeEngine(oem_profile=oem)
    try:
        report = engine.audit(content)
        if json_output:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            render_terminal_report(report, os.path.basename(file_path))
        return 0 if report.is_compliant else 2
    except Exception as e:
        print(f"{RED}AutoBridge Syntax Error: {e}{RESET}", file=sys.stderr)
        return 1


def run_repair(file_path: str, oem: str, output_path: str = None):
    if not os.path.exists(file_path):
        print(f"{RED}Error: File not found at '{file_path}'{RESET}", file=sys.stderr)
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    repairer = AutoRepairEngine(oem_profile=oem)
    res = repairer.repair(content)

    print("\n" + "=" * 78)
    print(f"{BOLD}{CYAN}    🛠️ AUTOBRIDGE DETERMINISTIC AUTO-REPAIR ENGINE{RESET}")
    print("=" * 78)
    print(f"  {BOLD}Source File:{RESET}      {file_path}")
    print(f"  {BOLD}OEM Profile:{RESET}      {oem}")
    print(f"  {BOLD}Output Target:{RESET}    {output_path or 'STDOUT'}")
    print(f"  {BOLD}Total Repairs:{RESET}    {res['total_fixes']} applied")
    print("-" * 78)

    for idx, c in enumerate(res["changes"], 1):
        print(f"  {idx}. [{c['tag']}] {c['action']}")

    print("-" * 78)
    sha_hash = hashlib.sha256(res["repaired_edi"].encode("utf-8")).hexdigest().upper()
    print(f"  {BOLD}{GREEN}✅ SHA-256 Digest:{RESET} {sha_hash}")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as out:
            out.write(res["repaired_edi"])
        print(f"  {BOLD}{GREEN}✅ Clean EDI saved to:{RESET} {output_path}")

    print("=" * 78 + "\n")
    return 0


def main():
    args = sys.argv[1:]
    if not args or args[0] in ["-h", "--help"]:
        print(f"""{BOLD}AutoBridge CLI{RESET} — Precision Pre-Flight EDI 856 Firewall

{BOLD}USAGE:{RESET}
  python -m autobridge.cli audit <file> [--oem PROFILE] [--json]
  python -m autobridge.cli repair <file> [--out OUTFILE] [--oem PROFILE]
  python -m autobridge.cli <file> [--oem PROFILE] [--json]

{BOLD}SUPPORTED OEM RULESETS:{RESET}
  FORD-AIAG-B10 (Default)
  GM-1724
  STELLANTIS-DESADV
""")
        sys.exit(0)

    # Subcommand routing
    if args[0] == "audit":
        parser = argparse.ArgumentParser()
        parser.add_argument("command", choices=["audit"])
        parser.add_argument("file")
        parser.add_argument("--oem", default="FORD-AIAG-B10")
        parser.add_argument("--json", action="store_true")
        parsed = parser.parse_args(args)
        sys.exit(run_audit(parsed.file, parsed.oem, parsed.json))

    elif args[0] == "repair":
        parser = argparse.ArgumentParser()
        parser.add_argument("command", choices=["repair"])
        parser.add_argument("file")
        parser.add_argument("--out", default=None)
        parser.add_argument("--oem", default="FORD-AIAG-B10")
        parsed = parser.parse_args(args)
        sys.exit(run_repair(parsed.file, parsed.oem, parsed.out))

    else:
        # Default fallback: treat as audit
        parser = argparse.ArgumentParser()
        parser.add_argument("file")
        parser.add_argument("--oem", default="FORD-AIAG-B10")
        parser.add_argument("--json", action="store_true")
        parsed = parser.parse_args(args)
        sys.exit(run_audit(parsed.file, parsed.oem, parsed.json))


if __name__ == "__main__":
    main()
