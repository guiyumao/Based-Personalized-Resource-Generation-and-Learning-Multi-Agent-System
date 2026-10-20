"""Validate the deliverable JSON schema and prove no throwaway objects were left behind."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

REQ = {"middleware", "level", "container_image", "app_code_path", "operation",
       "status", "evidence", "error", "substitution"}

d = json.load(open("artifacts/global-testing/middleware-integration.json", encoding="utf-8"))
print("top-level keys:", sorted(d.keys()))
print("target:", d["target"], "| generated_at:", d["generated_at"])
print("rows:", len(d["results"]))
for r in d["results"]:
    missing = REQ - set(r.keys())
    assert not missing, (r["middleware"], missing)
    assert r["level"] in ("L1", "L2", "L3", "unverified"), r["level"]
    assert r["status"] in ("pass", "fail", "blocked"), r["status"]
    assert set(r["substitution"]) == {"used", "image", "semantic_diff"}, r["substitution"]
print("SCHEMA OK for all rows\n")
for r in d["results"]:
    print(f"{r['middleware']:<20} {r['level']:<11} {r['status']:<7} "
          f"sub={r['substitution']['used']!s:<5} app={r['app_code_path']}")

print("\n--- residue check ---")
from common.config import get_settings  # noqa: E402

s = get_settings()

# Neo4j
try:
    from neo4j import GraphDatabase
    drv = GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_username, s.neo4j_password))
    with drv.session() as sess:
        n = sess.run(
            "MATCH (kp:KnowledgePoint) WHERE kp.name STARTS WITH 'QA_R4_MW_' "
            "RETURN count(kp) AS c"
        ).single()["c"]
    drv.close()
    print(f"neo4j residual QA_R4_MW_ nodes: {n}")
except Exception as exc:  # noqa: BLE001
    print("neo4j residue check failed:", exc)

# Chroma scratch (persistent)
try:
    import chromadb
    scratch = str(ROOT / "artifacts" / "global-testing" / "chroma-scratch")
    names = [c.name for c in chromadb.PersistentClient(path=scratch).list_collections()]
    print(f"chroma scratch residual collections: {names}")
except Exception as exc:  # noqa: BLE001
    print("chroma residue check failed:", exc)

# MinIO
try:
    from minio import Minio
    mc = Minio(s.minio_endpoint, access_key=s.minio_access_key,
               secret_key=s.minio_secret_key, secure=s.minio_secure)
    print(f"minio residual buckets: {[b.name for b in mc.list_buckets()]}")
except Exception as exc:  # noqa: BLE001
    print("minio residue check failed:", exc)

# Redis
try:
    import redis as redis_lib
    c = redis_lib.Redis.from_url(s.redis_url, socket_connect_timeout=3)
    print(f"redis residual qa:r4:* keys: {c.keys('qa:r4:*')}")
except Exception as exc:  # noqa: BLE001
    print("redis residue check failed:", exc)
