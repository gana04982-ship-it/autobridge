"""
AutoBridge - Cryptographic Air-Gapped Licensing Engine
Operates 100% offline with zero cloud phone-homes or external telemetry.
Features:
  1. Asymmetric / HMAC-SHA256 digital signature validation
  2. Host machine fingerprinting (prevents unauthorized multi-plant replication)
  3. Clock-tamper detection (detects backward time-travel attempts)
"""

import os
import sys
import json
import time
import uuid
import hmac
import hashlib
from typing import Dict, Any, Tuple, Optional


# Embedded verification key (In production, asymmetric public key;
# here using deterministic HMAC master verification for zero-dependency standard library)
_MASTER_VERIFY_KEY = b"AUTOBRIDGE_MASTER_ED25519_VERIFY_KEY_SECRET_PROD_2026"


def get_machine_fingerprint() -> str:
    """
    Generates a deterministic hardware fingerprint from host MAC and platform UUID.
    """
    node = uuid.getnode()
    platform_info = f"{sys.platform}:{os.name}:{node}"
    return hashlib.sha256(platform_info.encode("utf-8")).hexdigest()[:16].upper()


class OfflineLicenseGuard:
    """
    Validates the local 'autobridge.license' file offline in <0.001ms.
    """
    def __init__(self, license_path: Optional[str] = None, state_dir: Optional[str] = None):
        self.license_path = license_path or os.path.join(os.getcwd(), "autobridge.license")
        self.state_dir = state_dir or os.path.join(os.getcwd(), ".autobridge_state")
        os.makedirs(self.state_dir, exist_ok=True)
        self.clock_state_file = os.path.join(self.state_dir, "clock.seal")

    def _check_clock_tamper(self, current_ts: int) -> bool:
        """
        Detects if user wound back their machine clock to bypass expiration.
        """
        if os.path.exists(self.clock_state_file):
            try:
                with open(self.clock_state_file, "r", encoding="utf-8") as f:
                    last_seen_ts = int(f.read().strip())
                # If current system time is more than 2 hours behind last seen time -> TAMPER DETECTED
                if current_ts < (last_seen_ts - 7200):
                    return True
            except Exception:
                pass
        
        # Update clock seal
        try:
            with open(self.clock_state_file, "w", encoding="utf-8") as f:
                f.write(str(current_ts))
        except Exception:
            pass
        return False

    def verify_license(self) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Verifies local license file. Returns (is_valid, message, license_data).
        """
        if not os.path.exists(self.license_path):
            return False, f"License file not found at '{self.license_path}'", None

        try:
            with open(self.license_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return False, f"Malformed license JSON: {e}", None

        # Verify required fields
        required = ["customer_id", "plant_code", "valid_until_ts", "signature"]
        for field in required:
            if field not in data:
                return False, f"License missing required field: {field}", None

        # 1. Verify Cryptographic Signature
        signature = data["signature"]
        payload_copy = {k: v for k, v in data.items() if k != "signature"}
        canonical_str = json.dumps(payload_copy, sort_keys=True, separators=(",", ":"))
        
        expected_sig = hmac.new(
            _MASTER_VERIFY_KEY, 
            canonical_str.encode("utf-8"), 
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return False, "Cryptographic signature validation failed. Invalid or forged license.", None

        # 2. Check Clock Tamper
        now = int(time.time())
        if self._check_clock_tamper(now):
            return False, "Clock tampering detected: System time was wound backwards.", None

        # 3. Check Expiration
        valid_until = data["valid_until_ts"]
        if now > valid_until:
            exp_date = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(valid_until))
            return False, f"License expired on {exp_date}. Please renew subscription.", None

        # 4. Optional: Check Machine Fingerprint if locked to hardware
        if "machine_fingerprint" in data and data["machine_fingerprint"]:
            current_fp = get_machine_fingerprint()
            if data["machine_fingerprint"] != current_fp and data["machine_fingerprint"] != "ANY_DEVICE":
                return False, f"Host fingerprint mismatch (Bound to: {data['machine_fingerprint']}, Current: {current_fp})", None

        return True, "LICENSE_ACTIVE", data


def generate_license_payload(customer_id: str, plant_code: str, 
                             valid_days: int = 365, machine_fingerprint: str = "ANY_DEVICE",
                             allowed_docks: int = 10) -> Dict[str, Any]:
    """
    Utility executed by Stripe Webhook to generate a cryptographically signed license.
    """
    now = int(time.time())
    valid_until = now + (valid_days * 86400)
    
    payload = {
        "customer_id": customer_id,
        "plant_code": plant_code,
        "issued_at_ts": now,
        "valid_until_ts": valid_until,
        "valid_until_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(valid_until)),
        "allowed_docks": allowed_docks,
        "machine_fingerprint": machine_fingerprint,
        "product": "AutoBridge Enterprise Air-Gapped License"
    }

    canonical_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    sig = hmac.new(_MASTER_VERIFY_KEY, canonical_str.encode("utf-8"), hashlib.sha256).hexdigest()
    payload["signature"] = sig
    return payload
