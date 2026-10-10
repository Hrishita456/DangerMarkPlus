"""Fail before serving if the immutable pilot deployment bundle is incomplete."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = os.environ.get("PILOT_RUN_ID", "analysis-1616d67b7b28fb2442d9747f")


def validate_bundle():
    bundle_path = ROOT / "data/catalog/bundle.json"
    bundle = json.loads(bundle_path.read_text())
    records = [record for item in bundle["inputs"].values() for record in item["files"]]
    records.append(bundle["inputs"]["population"]["native_source_subset"])
    records.extend(bundle[key] for key in ("configuration", "source_catalogue", "validation_report", "toolchain_lock"))
    for record in records:
        path = (ROOT / record["path"]).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("Bundle path escapes deployment root")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
                raise ValueError(f"Deployment input checksum mismatch: {record['path']}")
    from app.services.consequences import read_run
    from app.services.evacuation import get_evacuation
    summary = read_run(RUN_ID, "summary")
    if summary["bundle_sha256"] != hashlib.sha256(bundle_path.read_bytes()).hexdigest():
        raise ValueError("Saved analysis and deployed bundle differ")
    for layer in ("localities", "road-impacts", "flood"):
        read_run(RUN_ID, layer)
    planning = get_evacuation(RUN_ID)
    if planning["run_id"] != RUN_ID or not planning["plans"]:
        raise ValueError("Deployment requires saved pilot plans")
    print(f"Deployment ready: {RUN_ID}, {len(planning['plans'])} plans", flush=True)


if __name__ == "__main__":
    validate_bundle()
    os.execvp("python", ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"])
