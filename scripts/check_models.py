#!/usr/bin/env python3
"""Model Check & Hardware Diagnostic Script per §50 & §52.

Inspects available GPUs, VRAM capacity, cached model checkpoints, and
verifies device compatibility for SatQuery-X AI pipelines.
"""

import os
import sys
from pathlib import Path

# Add backend to path so we can import model manager
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def check_system() -> None:
    print("==================================================")
    print("       SatQuery-X AI System & Model Diagnostics    ")
    print("==================================================")

    # 1. Python Environment
    print(f"Python Version: {sys.version.split()[0]}")

    # 2. PyTorch & CUDA Detection
    try:
        import torch
        print(f"PyTorch Version: {torch.__version__}")
        cuda_avail = torch.cuda.is_available()
        print(f"CUDA Available: {cuda_avail}")
        if cuda_avail:
            print(f"Device Name: {torch.cuda.get_device_name(0)}")
            free_b, total_b = torch.cuda.mem_get_info()
            print(f"VRAM Free: {free_b / (1024**3):.2f} GB / Total: {total_b / (1024**3):.2f} GB")
        else:
            print("Running in CPU Mode (low-hardware development)")
    except ImportError:
        print("PyTorch: Not installed in active interpreter")

    # 3. ModelManager Health
    try:
        from apps.models_ai.manager import model_manager
        health = model_manager.health_check()
        print("\nModelManager Health:")
        print(f"  Operational Mode: {health['mode']}")
        print(f"  Selected Device: {health['device']}")
        print(f"  Default Dtype: {health['dtype']}")
        print(f"  Cached Models: {health['loaded_models']}")
    except Exception as e:
        print(f"\nModelManager Check Error: {e}")

    # 4. Check Checkpoint Cache
    cache_dir = Path(os.getenv("MODEL_CACHE_DIR", "./checkpoints")).resolve()
    print(f"\nCheckpoint Cache Directory: {cache_dir}")
    if cache_dir.exists():
        entries = list(cache_dir.glob("*"))
        print(f"  Found {len(entries)} items in cache.")
        for item in entries[:10]:
            print(f"   - {item.name}")
    else:
        print("  Cache directory does not exist yet. Run `python scripts/download_models.py` to populate.")

    print("==================================================")


if __name__ == "__main__":
    check_system()
