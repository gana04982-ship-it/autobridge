# AutoBridge Core (`autobridge`)

> **The Mathematical Guarantee of Automotive Supply Chain Delivery.**  
> Zero-dependency ANSI X12 856 (Advance Ship Notice) AST parser & deterministic pre-flight validator for Ford AIAG and General Motors OEM receiving docks.

[![Tests](https://img.shields.io/badge/tests-26%20passed-brightgreen.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)]()
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0-success.svg)]()
[![License](https://img.shields.io/badge/license-BSL--1.1-purple.svg)]()

---

## 🎯 The Industrial Problem

Automotive parts manufacturers (Tier-1 and Tier-2 suppliers) operate on razor-thin 3%–6% margins. Every shipment leaving a supplier's loading dock must be accompanied by an electronic **EDI 856 Advance Ship Notice (ASN)** transmitted over AS2 networks.

When an 18-wheeler truck arrives at an OEM assembly plant (e.g. Ford Dearborn, GM Arlington):
* Automated overhead dock scanners read pallet 2D DataMatrix barcodes and compare them against the received EDI 856 stream.
* If a single qualifier is mismatched (e.g. `LIN02` is `ZZ` instead of `BP`), if the pallet packaging count in `TD102` drifts from actual tare loops, or if Bill of Lading (`REF*BM`) is missing:
* **The OEM automated receiving system rejects the delivery and levies a $5,000 to $15,000 chargeback fine per incident**, deducting it directly from the supplier's payment invoice.

Legacy EDI Value-Added Networks (VANs) like SPS Commerce and OpenText act as passive post offices: they disclaim all chargeback liability and transmit invalid files without semantic inspection.

**AutoBridge is the pre-flight firewall that prevents dock fines before the truck leaves the gate.**

---

## 🏛️ Architecture: 4-Tier Verification Pipeline

AutoBridge processes EDI streams through a deterministic, four-stage validation pipeline:

```
Raw ANSI X12 Stream
        │
        ▼
[Tier 1: Dynamic Delimiter Extractor]
  Extracts element, component, and segment terminators from ISA header bytes 3, 104, 105.
        │
        ▼
[Tier 2: Envelope Integrity Validator]
  Validates ISA/IEA control numbers, GS/GE group tallies, and exact ST/SE segment counts (SE01).
        │
        ▼
[Tier 3: Stateful HL Graph Tree-Builder]
  Reconstructs parent-child topological loops: Shipment (S) -> Order (O) -> Tare (T) -> Pack (P) -> Item (I).
        │
        ▼
[Tier 4: OEM Semantic Dock Rules (Ford AIAG B-10 / GM 1724)]
  Cross-checks pallet tallies, gross weights, carrier SCAC codes, BOL presence, and barcode uniqueness.
        │
        ▼
AuditReport (Green "Certified Safe to Ship" OR Actionable Remediation Audit)
```

---

## 🚀 Quickstart & CLI Usage

AutoBridge has **zero external dependencies** and runs on Python 3.9+.

### 1. Scan a Production ASN File
```bash
python -m autobridge.cli samples/ford_clean_shipment.edi
```

**Output:**
```text
==============================================================================
    🚀 AUTOBRIDGE PRE-FLIGHT EDI INSPECTOR — DOCK CERTIFICATION
==============================================================================
  Target File:      ford_clean_shipment.edi
  OEM Rule Profile: FORD-AIAG-B10
  Shipment ID:      SHIP12345
  Carrier SCAC:     FXFW | BOL: BOL-987654
  Ship-To Plant:    00123 (FORD DEARBORN TRUCK)
  Pallet Count:     Declared: 1 | In Tree: 1
  Parts Shipped:    100 units across 1 part number(s)
------------------------------------------------------------------------------

  ✅ STATUS: 100% COMPLIANT — CERTIFIED SAFE TO SHIP
  No OEM chargeback violations detected. Ready for dock receiving.

==============================================================================
```

### 2. Detect a Dock Rejection Trap File
```bash
python -m autobridge.cli samples/ford_dock_rejection_trap.edi
```

**Output:**
```text
==============================================================================
    🚀 AUTOBRIDGE PRE-FLIGHT EDI INSPECTOR — DOCK CERTIFICATION
==============================================================================
  Target File:      ford_dock_rejection_trap.edi
  OEM Rule Profile: FORD-AIAG-B10
  Shipment ID:      SHIP99999
  Carrier SCAC:     FXFW | BOL: UNKNOWN
  Ship-To Plant:    00123 (FORD DEARBORN TRUCK)
  Pallet Count:     Declared: 2 | In Tree: 1
  Parts Shipped:    100 units across 1 part number(s)
------------------------------------------------------------------------------

  🛑 STATUS: DOCK REJECTION RISK — 3 CRITICAL VIOLATION(S)
  Transmitting this file will trigger an automated OEM chargeback fine.

DETAILED VIOLATION AUDIT:
------------------------------------------------------------------------------
1. [FORD-003-MISSING-BOL] Line 5 in segment REF
   Severity: CRITICAL
   Dock Impact: Missing mandatory Bill of Lading number (REF*BM) at Shipment level.
   Violating Value: 'Missing'
   Specification Rule: Ford AIAG B-10: REF*BM mandatory for dock receiving
   👉 Remediation Action: Add REF*BM segment with Bill of Lading number under HL*...*S.

2. [FORD-008-PALLET-COUNT-MISMATCH] Line 7 in segment TD1
   Severity: CRITICAL
   Dock Impact: Packaging tally mismatch: TD102 declares 2 pallet(s), but HL tree contains 1 Tare (T) level pallet node(s).
   Violating Value: 'Declared:2 vs Actual:1'
   Specification Rule: Ford AIAG: Declared lading count must equal Tare HL nodes
   👉 Remediation Action: Update TD102 from 2 to 1.

3. [FORD-018-INVALID-PART-QUALIFIER] Line 18 in segment LIN
   Severity: CRITICAL
   Dock Impact: LIN02 qualifier must be 'BP' (Buyer's Part Number). Found 'ZZ'.
   Violating Value: 'ZZ'
   Specification Rule: Ford AIAG: LIN02 must equal 'BP'
   👉 Remediation Action: Set LIN02 qualifier to 'BP'.

==============================================================================
```

### 3. Machine-Readable JSON Mode (For ERP / AS2 Proxy Gateways)
```bash
python -m autobridge.cli samples/ford_dock_rejection_trap.edi --json
```

---

## 🐍 Python API Integration

```python
from autobridge.engine import AutoBridgeEngine

engine = AutoBridgeEngine(oem_profile="FORD-AIAG-B10")
report = engine.audit(raw_edi_content)

if report.is_compliant:
    print(f"Certified: Shipment {report.shipment_summary.shipment_id} safe to transmit.")
    # Forward to AS2 endpoint
else:
    print(f"Intercepted {report.critical_errors} critical dock violations!")
    for v in report.violations:
        print(f" - [{v.rule_id}] Line {v.line_number}: {v.message}")
        print(f"   Fix: {v.fix_recommendation}")
```

---

## 🧪 Precision Test Harness

Run the exhaustive test suite:
```bash
python -m unittest discover tests
```

Tests cover:
* Dynamic delimiter extraction (Standard `*`, `~`, non-standard `|`, `^`, composite separators).
* Continuous byte-stream transmissions vs multi-line formatted files.
* Envelope control number sync (`ISA13` $\leftrightarrow$ `IEA02`, `GS06` $\leftrightarrow$ `GE02`, `ST02` $\leftrightarrow$ `SE02`).
* Exact segment count arithmetic (`SE01`).
* Recursive `HL` tree graph topology, orphan nodes, multiple roots, and sequential ordering.
* Semantic AIAG checks: weight balancing, packaging count reconciliation, barcode uniqueness, part qualifiers.

---

## 📄 License
Licensed under the **Business Source License 1.1 (BSL-1.1)**.  
Free for individual developers, testing, and internal evaluation. Commercial hosting as a competing managed cloud gateway requires a commercial license agreement.
