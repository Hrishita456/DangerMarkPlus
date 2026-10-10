"""Read-only HTTP check. Usage: python infra/smoke.py BASE_URL [CORS_ORIGIN] [--require-gzip]."""
import gzip
import json
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen

RUN = "analysis-1616d67b7b28fb2442d9747f"


def main():
    base = sys.argv[1].rstrip("/")
    positional = [arg for arg in sys.argv[2:] if arg != "--require-gzip"]
    origin = positional[0] if positional else None

    def get(path):
        headers = {"Accept-Encoding": "gzip"}
        if origin:
            headers["Origin"] = origin
        request = Request(base + "/api/v1" + path, headers=headers)
        with urlopen(request, timeout=60) as response:
            if origin and response.headers.get("Access-Control-Allow-Origin") != origin:
                raise AssertionError("Configured frontend CORS origin was not allowed")
            payload = response.read()
            encoding = response.headers.get("Content-Encoding")
            if path.endswith("/road-impacts"):
                if "--require-gzip" in sys.argv:
                    assert encoding == "gzip", "Road impacts must preserve Content-Encoding: gzip"
                print(json.dumps({"path": path, "content_encoding": encoding,
                                  "compressed_bytes": len(payload)}))
            if encoding == "gzip":
                payload = gzip.decompress(payload)
            return json.loads(payload)

    assert get("/health")["status"] == "ok"
    assert get("/runs/demo-yamuna-2023/summary")["run_id"] == "demo-yamuna-2023"
    root = f"/runs/{RUN}"
    summary = get(root + "/summary")
    assert summary["run_id"] == RUN and summary["is_demo"] is False
    for layer in ("localities", "road-impacts", "flood", "safe-sites"):
        geo = get(root + "/" + layer)
        assert geo["type"] == "FeatureCollection" and geo["features"], layer
    planning = get(root + "/evacuation")
    assert planning["run_id"] == RUN and len(planning["plans"]) == 12
    assert sum(p["backup_route"] is not None for p in planning["plans"]) == 8
    for plan in planning["plans"]:
        locality = quote(plan["locality"]["locality_id"], safe="")
        assert get(root + f"/localities/{locality}/plan") == plan
        assert plan["primary_route"] is not None
        assert plan["demand_people"] is None
        assert plan["capacity_status"] == "unknown"
        assert plan["deadline"]["latest_departure"] is None
    print(json.dumps({"status": "pass", "base_url": base, "run_id": RUN,
                      "primary_routes": 12, "independent_backups": 8,
                      "cors_origin_checked": origin}))


if __name__ == "__main__":
    main()
