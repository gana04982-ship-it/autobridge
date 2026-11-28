"""
AutoBridge Standalone Offline Desktop & CLI Launcher.
- Double-clicking AutoBridge-Windows-x64.exe (no arguments, or `serve` / `--ui`)
  starts the loopback offline server on 127.0.0.1 and opens the local Studio UI.
- Passing any CLI subcommand (`audit`, `repair`, `watch`, `forensic-audit`,
  `license`, `diag`) runs the headless air-gapped CLI directly.
"""

import os
import sys
import threading
import webbrowser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from autobridge import cli
from autobridge.server import bind_server


def launch_offline_studio(port: int = 8085) -> None:
    """Start the local loopback server and open the air-gapped Studio in browser."""
    server = bind_server(port=port, host="127.0.0.1")
    actual_port = server.server_address[1]
    studio_url = f"http://127.0.0.1:{actual_port}/inspector.html"

    print("=" * 68)
    print("  AUTOBRIDGE OFFLINE PRE-FLIGHT ENGINE (100% AIR-GAPPED LOOPBACK)")
    print("=" * 68)
    print(f"  Local Studio URL : {studio_url}")
    print("  Network Status   : Loopback only (zero external uploads)")
    print("  Close this window or press Ctrl+C to stop AutoBridge.")
    print("=" * 68)

    threading.Timer(0.4, lambda: webbrowser.open(studio_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down AutoBridge.")
        server.shutdown()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if not args or args[0] in ("serve", "--ui"):
        port = 8085
        if len(args) >= 2 and args[1].isdigit():
            port = int(args[1])
        launch_offline_studio(port=port)
        return
    cli.main()


if __name__ == "__main__":
    main()
