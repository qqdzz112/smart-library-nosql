"""Export every collection of the library database to Extended JSON.

The ZIP submission must contain the database itself, not only the import scripts,
so this dumps each collection (including GridFS metadata) as JSON that can be
restored with mongoimport or read by any Extended JSON parser.

Usage:
    python scripts/export_archive.py --out data/dump
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from bson import json_util
from pymongo import MongoClient

from config import settings

COLLECTIONS = [
    "books",
    "readers",
    "borrow_logs",
    "category_stats",
    "audit_logs",
    "fs.files",
    "fs.chunks",
]


def export(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    client = MongoClient(settings.uri, serverSelectionTimeoutMS=5000)
    db = client[settings.db_name]
    summary = {}
    for name in COLLECTIONS:
        docs = list(db[name].find({}))
        path = out_dir / f"{name.replace('.', '_')}.json"
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json_util.dumps(docs, ensure_ascii=False, indent=1))
        summary[name] = len(docs)
        print(f"{name:16s} {len(docs):>6} docs -> {path.name}")
    meta = {
        "database": settings.db_name,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "server": client.server_info()["version"],
        "counts": summary,
        "indexes": {name: db[name].index_information() for name in COLLECTIONS},
    }
    with (out_dir / "_manifest.json").open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, default=str)
    print("manifest -> _manifest.json")
    client.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("data", "dump"))
    args = ap.parse_args()
    export(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
