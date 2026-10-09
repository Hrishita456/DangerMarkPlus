"""Shared file/provenance helpers for the offline-capable pilot pipeline."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(os.environ.get("PILOT_CONFIG", ROOT / "data/catalog/pilot.json")).resolve()
CATALOG = CONFIG_PATH.parent
USER_AGENT = "BharatBuilds-pilot-research/0.1"


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=path.name, suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path):
    path = Path(path)
    return {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256(path)}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def config():
    value = read_json(CONFIG_PATH)
    region_id = value["id"]
    if not region_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in region_id):
        raise ValueError("Region ID must be a safe lowercase directory name")
    return value


RAW = ROOT / "data/raw" / config()["id"]
PROCESSED = ROOT / "data/processed" / config()["id"]


def manifest_path(dataset_id):
    return CATALOG / "manifests" / f"{dataset_id}.json"


def verified_existing(dataset_id, path):
    if not Path(path).exists():
        return False
    manifest = manifest_path(dataset_id)
    if not manifest.exists():
        raise RuntimeError(f"Existing source without manifest: {path}. Preserve it and investigate before reacquiring.")
    record = next((item for item in read_json(manifest)["raw_files"] if ROOT / item["path"] == Path(path)), None)
    if record is None or sha256(path) != record["sha256"]:
        raise RuntimeError(f"Source checksum mismatch: {path}; refusing to silently replace it")
    print(f"Cached and verified: {dataset_id}", flush=True)
    return True


def record_acquisition(dataset_id, source, path, details):
    write_json(manifest_path(dataset_id), {
        "id": dataset_id, **source, "acquired_at": utc_now(),
        "raw_files": [file_record(path)], "processed_crs": None,
        "processed_files": [], "preprocessing_steps": [], **details,
    })


def record_processing(dataset_id, paths, steps, crs, **details):
    path = manifest_path(dataset_id)
    manifest = read_json(path)
    manifest.update(processed_files=[file_record(item) for item in paths],
                    preprocessing_steps=steps, processed_crs=crs,
                    configuration_sha256=sha256(CONFIG_PATH), **details)
    write_json(path, manifest)
