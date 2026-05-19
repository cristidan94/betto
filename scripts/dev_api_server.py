from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.vendor import add_vendor_path

add_vendor_path()

import uvicorn

uvicorn.run("api.main:app", host="127.0.0.1", port=int(os.environ.get("BETTO_API_PORT", "8000")))
