"""Network-enabled setup command, separate from the offline application."""
import argparse
import json
import os
from pathlib import Path

from .models import CATALOG, REPOSITORIES, MODEL_ROOT, REQUIRED, file_hash, ready


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["all", *CATALOG], default="all")
    args = parser.parse_args()
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import HfApi, snapshot_download
    for name in CATALOG if args.model == "all" else [args.model]:
        if ready(name):
            print(f"{name}: already prepared", flush=True)
            continue
        repo = REPOSITORIES[name]
        revision = HfApi().model_info(repo).sha
        target = MODEL_ROOT / name
        print(f"Preparing {repo} @ {revision}", flush=True)
        snapshot_download(repo, revision=revision, local_dir=target,
                          allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"], max_workers=2)
        if not all((target / n).is_file() for n in REQUIRED):
            raise RuntimeError("Missing model files")
        files = {p.name: {"bytes": p.stat().st_size, "sha256": file_hash(p)} for p in target.iterdir() if p.is_file() and p.name != "manifest.json"}
        manifest = {"id": name, "repository": repo, "revision": revision, "license": "MIT", "files": files}
        temporary = target / "manifest.partial"
        temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        temporary.replace(target / "manifest.json")
        print(f"{name}: ready", flush=True)


if __name__ == "__main__":
    main()
