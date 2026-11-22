"""
AutoBridge - Folder-Watcher Sidecar Daemon
Runs as a lightweight background service on plant shipping PCs or on-prem servers.
Continuously intercepts raw EDI 856 files, executes sub-millisecond AST repair,
archives raw originals, stamps SHA-256 clearance seals, and feeds AS2 gateways.
"""

import os
import sys
import time
import glob
import logging
from typing import Optional, Callable

from autobridge.repair import AutoRepairEngine
from autobridge.core.safety import (
    atomic_write_file, 
    DualWriteArchiver, 
    FailOpenWatchdog, 
    QuarantineManager
)
from autobridge.core.licensing import OfflineLicenseGuard


logger = logging.getLogger("AutoBridgeWatcher")


class FolderWatcherDaemon:
    """
    Zero-dependency polling sidecar daemon with industrial fail-open protection.
    """
    def __init__(self, in_dir: str, out_dir: str, 
                 archive_dir: Optional[str] = None, 
                 quarantine_dir: Optional[str] = None,
                 oem_profile: str = "FORD-AIAG-B10",
                 poll_interval_sec: float = 0.5):
        self.in_dir = os.path.abspath(in_dir)
        self.out_dir = os.path.abspath(out_dir)
        self.archive_dir = os.path.abspath(archive_dir or os.path.join(self.in_dir, "../archive"))
        self.quarantine_dir = os.path.abspath(quarantine_dir or os.path.join(self.in_dir, "../quarantine"))
        self.log_dir = os.path.join(self.archive_dir, "logs")

        os.makedirs(self.in_dir, exist_ok=True)
        os.makedirs(self.out_dir, exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)
        os.makedirs(self.quarantine_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        self.poll_interval = poll_interval_sec
        self.oem_profile = oem_profile
        self.repairer = AutoRepairEngine(oem_profile=self.oem_profile)
        
        self.archiver = DualWriteArchiver(self.archive_dir)
        self.watchdog = FailOpenWatchdog(self.log_dir)
        self.quarantine = QuarantineManager(self.quarantine_dir)
        self.license_guard = OfflineLicenseGuard()

        self._running = False

    def process_file(self, file_path: str) -> bool:
        """
        Processes a single EDI manifest with complete fail-open and dual-write guarantees.
        """
        filename = os.path.basename(file_path)
        out_path = os.path.join(self.out_dir, filename)

        # 1. Quick sanity check on file size
        try:
            size = os.path.getsize(file_path)
            if size == 0:
                self.quarantine.quarantine(file_path, "EMPTY_FILE_ZERO_BYTES")
                os.remove(file_path)
                return False
        except Exception:
            return False

        # Read raw content
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                raw_content = f.read().strip()
        except Exception as e:
            self.quarantine.quarantine(file_path, f"UNREADABLE_FILE: {e}")
            try:
                os.remove(file_path)
            except Exception:
                pass
            return False

        # Basic EDI envelope check
        if "ST*" not in raw_content or "SE*" not in raw_content:
            self.quarantine.quarantine(file_path, "NOT_AN_EDI_856_MANIFEST", {"preview": raw_content[:100]})
            try:
                os.remove(file_path)
            except Exception:
                pass
            return False

        # 2. Execute with FailOpenWatchdog
        success, status, result = self.watchdog.execute_safe_dispatch(
            file_path, 
            out_path, 
            self.repairer.repair
        )

        if success and result:
            # 3. Dual-Write Immutable Archive
            self.archiver.archive(
                filename, 
                raw_content, 
                result["repaired_edi"], 
                result.get("changes", [])
            )
            logger.info(f"✅ Cleared & Repaired: {filename} -> {out_path} ({result['total_fixes']} fixes)")
        else:
            logger.warning(f"⚠️ Fail-Open Dispatched: {filename} -> {out_path} ({status})")

        # 4. Remove processed file from in_dir to prevent reprocessing
        try:
            os.remove(file_path)
        except Exception:
            pass

        return True

    def run_once(self) -> int:
        """
        Scans in_dir for pending .856 / .edi / .txt files and processes them.
        Returns count of processed files.
        """
        patterns = ["*.856", "*.edi", "*.txt", "*.x12"]
        candidates = []
        for p in patterns:
            candidates.extend(glob.glob(os.path.join(self.in_dir, p)))

        processed = 0
        for cand in candidates:
            if cand.endswith(".tmp") or cand.endswith(".bypass.warning"):
                continue
            if self.process_file(cand):
                processed += 1
        return processed

    def start(self, max_iterations: Optional[int] = None) -> None:
        """
        Continuous daemon loop.
        """
        self._running = True
        logger.info(f"🚀 AutoBridge Daemon Active: Watching '{self.in_dir}' -> '{self.out_dir}'")
        logger.info(f"OEM Profile: {self.oem_profile} | Polling interval: {self.poll_interval}s")
        
        iterations = 0
        try:
            while self._running:
                self.run_once()
                iterations += 1
                if max_iterations and iterations >= max_iterations:
                    break
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logger.info("🛑 AutoBridge Daemon Stopped by User.")
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False
