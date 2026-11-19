"""Root entrypoint to launch ANVEXA AI Demo."""

from __future__ import annotations

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(root_dir))

from scripts.run_demo import seed

if __name__ == "__main__":
    print("\n[1/2] Seeding demonstration data...")
    seed()

    print("\n[2/2] Starting ANVEXA AI Application Server...")
    print("Web Dashboard: http://127.0.0.1:8000/")
    print("API Documentation: http://127.0.0.1:8000/docs\n")

    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=False)
