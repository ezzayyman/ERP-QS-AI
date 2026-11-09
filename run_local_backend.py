import sys
import os

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import uvicorn
from backend.app.main import app

if __name__ == "__main__":
    print("\n" + "=" * 65)
    print(">> GMI FloorTakeoff & Area Calculation Server")
    print(">> GMI Design and Implementation LLC — Dubai, UAE")
    print(">> API available at: http://localhost:8000")
    print(">> Swagger docs at:  http://localhost:8000/docs")
    print("=" * 65 + "\n")
    app_dir = os.path.join(BASE_DIR, "backend", "app")
    uvicorn.run(
        "backend.app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[app_dir],
        reload_includes=["*.py"],
        reload_excludes=["*.db", "*.db*", "*.sqlite", "*.png", "*.jpg", "*.pdf", "*.dxf", "*.xlsx", "*.csv"],
    )
