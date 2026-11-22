"""
AutoBridge - Core Safety, Robustness & Fail-Open Watchdog
Protects the manufacturing dock from worst-case operational failures:
  1. Atomic file writes (zero partial-file corruption on power cut)
  2. Dual-write non-destructive archiving (raw file always preserved)
  3. Fail-open watchdog (never halts the dock on unexpected exception)
  4. Conservative quarantine routing (no reckless guessing on ambiguous data)
"""

import os
import sys
import json
import time
import shutil
import hashlib
import traceback
from typing import Dict, Any, Optional, Tuple


def atomic_write_file(file_path: str, content: str) -> None:
    """
    Writes content to a temporary file on the same filesystem and atomically
    renames it over the target path. Prevents half-written corrupted files
    if power is lost mid-write.
    """
    directory = os.path.dirname(os.path.abspath(file_path))
    os.makedirs(directory, exist_ok=True)
    temp_path = f"{file_path}.tmp.{os.getpid()}_{int(time.time() * 1000)}"
    
    with open(temp_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
        
    os.replace(temp_path, file_path)


class DualWriteArchiver:
    """
    Maintains an immutable historical audit trail without destroying the original ERP output.
    """
    def __init__(self, archive_dir: str):
        self.archive_dir = os.path.abspath(archive_dir)
        self.orig_dir = os.path.join(self.archive_dir, "original")
        self.diff_dir = os.path.join(self.archive_dir, "diffs")
        os.makedirs(self.orig_dir, exist_ok=True)
        os.makedirs(self.diff_dir, exist_ok=True)

    def archive(self, original_filename: str, original_content: str, 
                repaired_content: str, changes: list) -> Dict[str, str]:
        ts = time.strftime("%Y%m%d_%H%M%S")
        orig_hash = hashlib.sha256(original_content.encode("utf-8")).hexdigest()[:12]
        base_name = os.path.basename(original_filename)
        
        orig_save_name = f"{ts}_{orig_hash}_{base_name}"
        orig_save_path = os.path.join(self.orig_dir, orig_save_name)
        atomic_write_file(orig_save_path, original_content)

        diff_save_name = f"{ts}_{orig_hash}_{base_name}.diff.json"
        diff_save_path = os.path.join(self.diff_dir, diff_save_name)
        
        diff_payload = {
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_file": original_filename,
            "original_sha256": hashlib.sha256(original_content.encode("utf-8")).hexdigest(),
            "repaired_sha256": hashlib.sha256(repaired_content.encode("utf-8")).hexdigest(),
            "total_modifications": len(changes),
            "changes": changes
        }
        atomic_write_file(diff_save_path, json.dumps(diff_payload, indent=2))
        
        return {
            "original_archive": orig_save_path,
            "diff_archive": diff_save_path,
            "sha256": diff_payload["repaired_sha256"]
        }


class FailOpenWatchdog:
    """
    THE GOLDEN RULE OF AUTOMOTIVE SHIPPING: NEVER HALT THE DOCK.
    If AutoBridge encounters an unhandled exception or malformed parser crash,
    the watchdog catches it, logs a forensic crash trace, and passes the
    ORIGINAL file straight to the ready queue so trucks depart on time.
    """
    def __init__(self, log_dir: str):
        self.log_dir = os.path.abspath(log_dir)
        os.makedirs(self.log_dir, exist_ok=True)
        self.crash_log = os.path.join(self.log_dir, "crash.log")
        self.bypass_log = os.path.join(self.log_dir, "bypass_events.jsonl")

    def execute_safe_dispatch(self, file_path: str, out_path: str, 
                              process_fn, *args, **kwargs) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Executes process_fn(file_path). If it raises ANY exception, fails open
        by copying raw file to out_path and logging event.
        Returns: (success_bool, status_message, result_dict_or_none)
        """
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            raw_content = f.read()

        try:
            result = process_fn(raw_content, *args, **kwargs)
            # If successful, atomic write to destination
            atomic_write_file(out_path, result["repaired_edi"])
            return True, "CLEARED_AND_REPAIRED", result

        except Exception as exc:
            # WORST-CASE TRIGGERED: CRASH DETECTED
            err_trace = traceback.format_exc()
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            
            # 1. Log forensic crash stack
            with open(self.crash_log, "a", encoding="utf-8") as clog:
                clog.write(f"\n--- [CRASH EVENT {ts}] ---\nFile: {file_path}\nError: {exc}\n{err_trace}\n")

            # 2. Log structured bypass event
            bypass_record = {
                "timestamp_utc": ts,
                "file": file_path,
                "destination": out_path,
                "error": str(exc),
                "action": "FAIL_OPEN_BYPASS_ENGAGED"
            }
            with open(self.bypass_log, "a", encoding="utf-8") as blog:
                blog.write(json.dumps(bypass_record) + "\n")

            # 3. FAIL OPEN: Pass original file untouched so dock truck leaves
            atomic_write_file(out_path, raw_content)
            
            # 4. Create companion bypass stamp file
            bypass_stamp = f"{out_path}.bypass.warning"
            atomic_write_file(bypass_stamp, f"AUTOBRIDGE FAIL-OPEN BYPASS ENGAGED: {exc}")

            return False, f"FAIL_OPEN_ENGAGED: {exc}", None


class QuarantineManager:
    """
    Handles unrecoverably mangled or empty manifests by moving them to quarantine
    and issuing a human-readable diagnosis for the dock shipping supervisor.
    """
    def __init__(self, quarantine_dir: str):
        self.quarantine_dir = os.path.abspath(quarantine_dir)
        os.makedirs(self.quarantine_dir, exist_ok=True)

    def quarantine(self, file_path: str, reason: str, details: Optional[Dict[str, Any]] = None) -> str:
        base_name = os.path.basename(file_path)
        ts = time.strftime("%Y%m%d_%H%M%S")
        target_name = f"{ts}_QUARANTINED_{base_name}"
        target_path = os.path.join(self.quarantine_dir, target_name)
        
        # Copy to quarantine
        shutil.copy2(file_path, target_path)
        
        # Generate companion diagnostic report
        diag_path = f"{target_path}.diagnosis.json"
        diag_payload = {
            "quarantine_time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "original_file": file_path,
            "quarantined_file": target_path,
            "reason": reason,
            "details": details or {}
        }
        atomic_write_file(diag_path, json.dumps(diag_payload, indent=2))
        return target_path
