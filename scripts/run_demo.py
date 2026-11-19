"""Launch script for ANVEXA AI Demo.

Seeds the database with sample verified manuscript and starts the local web server.
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

    print("\n[2/2] Starting ANVEXA AI Application Server...")
    print("Web Dashboard: http://127.0.0.1:8000/")
    print("API Documentation: http://127.0.0.1:8000/docs\n")

    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=False)
