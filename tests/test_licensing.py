"""
Unit tests for AutoBridge Cryptographic Offline Licensing Engine.
"""

import os
import shutil
import tempfile
import unittest

from autobridge.core.licensing import (
    OfflineLicenseGuard, 
    generate_license_payload, 
    get_machine_fingerprint
)


class TestLicensing(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.license_path = os.path.join(self.test_dir, "autobridge.license")
        self.state_dir = os.path.join(self.test_dir, "state")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_machine_fingerprint(self):
        fp = get_machine_fingerprint()
        self.assertIsInstance(fp, str)
        self.assertEqual(len(fp), 16)

    def test_valid_license_generation_and_verification(self):
        # 1. Generate signed license
        payload = generate_license_payload(
            customer_id="henniges-dearborn-04",
            plant_code="US-MI-48126",
            valid_days=30,
            allowed_docks=6
        )
        import json
        with open(self.license_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        # 2. Verify offline
        guard = OfflineLicenseGuard(self.license_path, self.state_dir)
        valid, msg, lic_data = guard.verify_license()
        
        self.assertTrue(valid)
        self.assertEqual(msg, "LICENSE_ACTIVE")
        self.assertEqual(lic_data["customer_id"], "henniges-dearborn-04")

    def test_tampered_signature_fails(self):
        payload = generate_license_payload("magna-troy", "US-MI-48083")
        payload["allowed_docks"] = 999  # Tamper with payload!
        
        import json
        with open(self.license_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        guard = OfflineLicenseGuard(self.license_path, self.state_dir)
        valid, msg, _ = guard.verify_license()
        self.assertFalse(valid)
        self.assertIn("signature validation failed", msg)

    def test_expired_license_fails(self):
        payload = generate_license_payload("visteon", "US-MI-48111", valid_days=-10)
        import json
        with open(self.license_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        guard = OfflineLicenseGuard(self.license_path, self.state_dir)
        valid, msg, _ = guard.verify_license()
        self.assertFalse(valid)
        self.assertIn("License expired", msg)


if __name__ == "__main__":
    unittest.main()
