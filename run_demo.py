"""Root entrypoint to launch ANVEXA AI Demo."""

from __future__ import annotations

import os
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(root_dir))

from scripts.run_demo import seed

if __name__ == "__main__":
    print("\n[1/2] Initializing demonstration environment...")
    try:
        seed()
    except Exception as exc:
        print(f"[!] Warning: Demo data seeding encountered an issue (server startup continuing): {exc}")

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    print("\n[2/2] Starting ANVEXA AI Application Server...")
    print(f"Web Dashboard: http://{host}:{port}/")
    print(f"API Documentation: http://{host}:{port}/docs\n")

    import uvicorn
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=False)
