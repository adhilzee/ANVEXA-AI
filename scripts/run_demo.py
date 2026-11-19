"""Launch script for ANVEXA AI Demo.

Seeds the database with sample verified manuscript and starts the web server.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))

# 1. Run Seeder
from scripts.seed_demo import seed

if __name__ == "__main__":
    print("\n[1/2] Seeding demonstration data...")
    seed()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    print("\n[2/2] Starting ANVEXA AI Application Server...")
    print(f"Web Dashboard: http://{host}:{port}/")
    print(f"API Documentation: http://{host}:{port}/docs\n")

    import uvicorn
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=False)
