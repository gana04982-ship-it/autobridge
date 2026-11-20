"""
AutoBridge - Pre-Flight EDI 856 Firewall & Auto-Repair Engine
AIAG B-10 & GM 1724 Automotive Supply Chain Compliance
"""

from autobridge.engine import AutoBridgeEngine
from autobridge.repair import AutoRepairEngine

__version__ = "1.0.0"
__all__ = ["AutoBridgeEngine", "AutoRepairEngine"]
