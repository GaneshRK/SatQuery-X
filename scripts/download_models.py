#!/usr/bin/env python3
"""Model Download Strategy per §52.

Downloads open-weight model checkpoints on-demand from Hugging Face into
MODEL_CACHE_DIR or HF_HOME. Models are never committed directly into Git.
"""

import argparse
import os
import sys
from pathlib import Path

TARGET_MODELS = {
    "router": {
        "repo_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "task": "Natural Language Query Router / SLM",
        "size": "~3.0 GB",
        "license": "Apache-2.0",
    },
    "change_detection": {
        "repo_id": "wgcban/ChangeFormerV6",
        "task": "Transformer-Based Change Detection",
        "size": "~160 MB",
        "license": "MIT",
    },
    "rs_embedding": {
        "repo_id": "OneScience-Group/RemoteCLIP",
        "task": "Remote-Sensing Multimodal Embeddings",
        "size": "~600 MB",
        "license": "MIT",
    },
    "grounding": {
        "repo_id": "IDEA-Research/grounding-dino-tiny",
        "task": "Text-Guided Visual Grounding",
        "size": "~680 MB",
        "license": "Apache-2.0",
    },
    "vlm_lightweight": {
        "repo_id": "Salesforce/blip-vqa-base",
        "task": "Remote-Sensing VQA / Captioning Fallback",
        "size": "~1.5 GB",
        "license": "BSD-3-Clause",
    },
}


def download_model(model_key: str, cache_dir: str) -> bool:
    if model_key not in TARGET_MODELS:
        print(f"[-] Unknown model key '{model_key}'. Available: {list(TARGET_MODELS.keys())}")
        return False

    info = TARGET_MODELS[model_key]
    repo_id = info["repo_id"]
    print(f"\n[+] Downloading {model_key} ({repo_id})...")
    print(f"    Task: {info['task']} | Approx Size: {info['size']} | License: {info['license']}")

    try:
        from huggingface_hub import snapshot_download
        path = snapshot_download(
            repo_id=repo_id,
            cache_dir=cache_dir,
            resume_download=True,
        )
        print(f"[OK] Successfully cached {model_key} at: {path}")
        return True
    except ImportError:
        print("[-] 'huggingface_hub' is not installed. Install with: pip install huggingface-hub")
        return False
    except Exception as e:
        print(f"[-] Failed to download {repo_id}: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Download SatQuery-X open-weight models from Hugging Face.")
    parser.add_argument("--model", type=str, default="all", help="Model key to download or 'all'")
    parser.add_argument("--cache-dir", type=str, default=os.getenv("MODEL_CACHE_DIR", "./checkpoints"), help="Target cache directory")
    args = parser.parse_args()

    cache_path = Path(args.cache_dir).resolve()
    cache_path.mkdir(parents=True, exist_ok=True)
    print(f"=== SatQuery-X Model Downloader ===")
    print(f"Target Cache Directory: {cache_path}")

    if args.model.lower() == "all":
        success_count = 0
        for k in TARGET_MODELS:
            if download_model(k, str(cache_path)):
                success_count += 1
        print(f"\nCompleted: {success_count}/{len(TARGET_MODELS)} models downloaded.")
    else:
        download_model(args.model, str(cache_path))


if __name__ == "__main__":
    main()
