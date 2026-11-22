"""
AutoBridge - Command-Line Interface (CLI)
Instant terminal pre-flight scanner, deterministic auto-repair engine,
folder-watcher sidecar daemon, and offline historical forensic auditor
for automotive EDI 856 Advance Ship Notices (AIAG B-10 & GM 1724).
"""

import sys
import os
import glob
import json
import zipfile
import argparse
import hashlib
import time

# Ensure parent directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from autobridge.engine import AutoBridgeEngine
from autobridge.repair import AutoRepairEngine
from autobridge.models.report import AuditReport
from autobridge.forensic import ForensicAuditor
from autobridge.watcher import FolderWatcherDaemon
from autobridge.core.licensing import OfflineLicenseGuard, generate_license_payload, get_machine_fingerprint


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


def run_forensic_audit(target_dir: str, oem: str, report_out: str = None, company: str = "Prospective Supplier"):
    if not os.path.exists(target_dir):
        print(f"{RED}Error: Path '{target_dir}' does not exist.{RESET}", file=sys.stderr)
        return 1

    file_paths = []
    if os.path.isfile(target_dir):
        file_paths = [target_dir]
    else:
        for p in ["*.856", "*.edi", "*.txt", "*.x12"]:
            file_paths.extend(glob.glob(os.path.join(target_dir, p)))

    if not file_paths:
        print(f"{YELLOW}Warning: No EDI files (.856, .edi, .txt) found in '{target_dir}'.{RESET}")
        return 1

    print(f"\n{BOLD}{CYAN}🚀 Running AutoBridge Forensic Chargeback Audit on {len(file_paths)} files...{RESET}\n")
    auditor = ForensicAuditor(oem_profile=oem)
    batch_result = auditor.audit_batch(file_paths)
    md_report = auditor.generate_executive_markdown_report(batch_result, company_name=company)

    print(md_report)

    if report_out:
        with open(report_out, "w", encoding="utf-8") as f:
            f.write(md_report)
        print(f"{BOLD}{GREEN}✅ Executive Report Saved to:{RESET} {report_out}")

    return 0


def run_watcher(in_dir: str, out_dir: str, archive_dir: str, quarantine_dir: str, oem: str):
    print(f"{BOLD}{CYAN}🚀 Initializing AutoBridge Sidecar Folder Watcher Daemon...{RESET}")
    print(f"  Input Directory:      {in_dir}")
    print(f"  Ready/Out Directory:  {out_dir}")
    print(f"  Archive Directory:    {archive_dir}")
    print(f"  Quarantine Directory: {quarantine_dir}")
    print(f"  OEM Rulebook:         {oem}")
    print("-" * 78)

    daemon = FolderWatcherDaemon(
        in_dir=in_dir,
        out_dir=out_dir,
        archive_dir=archive_dir,
        quarantine_dir=quarantine_dir,
        oem_profile=oem
    )
    daemon.start()
    return 0


def run_diag_export(out_path: str = "autobridge_diagnostic_bundle.zip"):
    print(f"{BOLD}{CYAN}📦 Compiling 1-Click Support Diagnostic Bundle...{RESET}")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. System info
        info = {
            "platform": sys.platform,
            "python_version": sys.version,
            "machine_fingerprint": get_machine_fingerprint(),
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        zf.writestr("system_info.json", json.dumps(info, indent=2))
        
        # 2. Add license status
        guard = OfflineLicenseGuard()
        valid, msg, lic = guard.verify_license()
        zf.writestr("license_status.txt", f"Status: {valid}\nMessage: {msg}\nPayload: {json.dumps(lic, indent=2)}")

        # 3. Add logs if present
        log_dir = os.path.join(os.getcwd(), "archive", "logs")
        if os.path.exists(log_dir):
            for lf in os.listdir(log_dir):
                full_lp = os.path.join(log_dir, lf)
                if os.path.isfile(full_lp):
                    zf.write(full_lp, arcname=f"logs/{lf}")

    print(f"{BOLD}{GREEN}✅ Diagnostic bundle created:{RESET} {os.path.abspath(out_path)}")
    return 0


def run_license(args):
    if args.action == "verify":
        guard = OfflineLicenseGuard()
        valid, msg, lic = guard.verify_license()
        if valid:
            print(f"{BOLD}{GREEN}✅ License ACTIVE & VALID:{RESET}")
            print(json.dumps(lic, indent=2))
            return 0
        else:
            print(f"{BOLD}{RED}❌ License Check FAILED:{RESET} {msg}")
            return 1

    elif args.action == "generate":
        if not args.customer or not args.plant:
            print(f"{RED}Error: --customer and --plant are required for license generation.{RESET}")
            return 1
        payload = generate_license_payload(
            customer_id=args.customer,
            plant_code=args.plant,
            valid_days=args.days or 365,
            machine_fingerprint=args.fingerprint or "ANY_DEVICE",
            allowed_docks=args.docks or 10
        )
        out_file = args.out or "autobridge.license"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"{BOLD}{GREEN}✅ Signed License File Created:{RESET} {out_file}")
        print(json.dumps(payload, indent=2))
        return 0

    elif args.action == "fingerprint":
        print(f"Host Machine Fingerprint: {BOLD}{CYAN}{get_machine_fingerprint()}{RESET}")
        return 0


def main():
    args = sys.argv[1:]
    if not args or args[0] in ["-h", "--help"]:
        print(f"""{BOLD}AutoBridge CLI{RESET} — Precision Pre-Flight EDI 856 Firewall & Offline Attack Engine

{BOLD}USAGE:{RESET}
  python -m autobridge.cli audit <file> [--oem PROFILE] [--json]
  python -m autobridge.cli repair <file> [--out OUTFILE] [--oem PROFILE]
  python -m autobridge.cli watch --in <IN_DIR> --out <OUT_DIR> [--archive <DIR>] [--quarantine <DIR>]
  python -m autobridge.cli forensic-audit <DIR_OR_FILE> [--out REPORT.md] [--company "Supplier Name"]
  python -m autobridge.cli license verify | generate | fingerprint
  python -m autobridge.cli diag [--export OUT.zip]

{BOLD}SUPPORTED OEM RULESETS:{RESET}
  FORD-AIAG-B10 (Default)
  GM-1724
  STELLANTIS-DESADV
""")
        sys.exit(0)

    cmd = args[0]

    if cmd == "audit":
        parser = argparse.ArgumentParser()
        parser.add_argument("command", choices=["audit"])
        parser.add_argument("file")
        parser.add_argument("--oem", default="FORD-AIAG-B10")
        parser.add_argument("--json", action="store_true")
        parsed = parser.parse_args(args)
        sys.exit(run_audit(parsed.file, parsed.oem, parsed.json))

    elif cmd == "repair":
        parser = argparse.ArgumentParser()
        parser.add_argument("command", choices=["repair"])
        parser.add_argument("file")
        parser.add_argument("--out", default=None)
        parser.add_argument("--oem", default="FORD-AIAG-B10")
        parsed = parser.parse_args(args)
        sys.exit(run_repair(parsed.file, parsed.oem, parsed.out))

    elif cmd == "forensic-audit":
        parser = argparse.ArgumentParser()
        parser.add_argument("command", choices=["forensic-audit"])
        parser.add_argument("target")
        parser.add_argument("--out", default=None)
        parser.add_argument("--oem", default="FORD-AIAG-B10")
        parser.add_argument("--company", default="Tier-1 Automotive Supplier")
        parsed = parser.parse_args(args)
        sys.exit(run_forensic_audit(parsed.target, parsed.oem, parsed.out, parsed.company))

    elif cmd == "watch":
        parser = argparse.ArgumentParser()
        parser.add_argument("command", choices=["watch"])
        parser.add_argument("--in", dest="in_dir", required=True)
        parser.add_argument("--out", dest="out_dir", required=True)
        parser.add_argument("--archive", default=None)
        parser.add_argument("--quarantine", default=None)
        parser.add_argument("--oem", default="FORD-AIAG-B10")
        parsed = parser.parse_args(args)
        sys.exit(run_watcher(parsed.in_dir, parsed.out_dir, parsed.archive, parsed.quarantine, parsed.oem))

    elif cmd == "license":
        parser = argparse.ArgumentParser()
        parser.add_argument("command", choices=["license"])
        parser.add_argument("action", choices=["verify", "generate", "fingerprint"])
        parser.add_argument("--customer", default=None)
        parser.add_argument("--plant", default=None)
        parser.add_argument("--days", type=int, default=365)
        parser.add_argument("--docks", type=int, default=10)
        parser.add_argument("--fingerprint", default="ANY_DEVICE")
        parser.add_argument("--out", default="autobridge.license")
        parsed = parser.parse_args(args)
        sys.exit(run_license(parsed))

    elif cmd == "diag":
        parser = argparse.ArgumentParser()
        parser.add_argument("command", choices=["diag"])
        parser.add_argument("--export", default="autobridge_diagnostic_bundle.zip")
        parsed = parser.parse_args(args)
        sys.exit(run_diag_export(parsed.export))

    else:
        # Fallback to audit
        parser = argparse.ArgumentParser()
        parser.add_argument("file")
        parser.add_argument("--oem", default="FORD-AIAG-B10")
        parser.add_argument("--json", action="store_true")
        parsed = parser.parse_args(args)
        sys.exit(run_audit(parsed.file, parsed.oem, parsed.json))


if __name__ == "__main__":
    main()
