# -*- coding: utf-8 -*-
"""GridFS 文件存储：电子书 PDF 与封面图片（任务四 F8）。

- 桶名固定为 fs（默认桶），一个文件被切成 fs.chunks 里的多个 255KB 分块；
- 元数据里写入 ISBN、文件类型（ebook/cover）、原始文件名，便于通过 books.ebook_name
  反查，也便于验收时按书检索；
- 下载后做「字节数 + MD5」双重校验，证明存取无损。
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
from datetime import datetime, timezone

import gridfs
from gridfs.errors import NoFile as GridFSNoFileError

from audit_logger import log_action
from config import settings
from mongodb_connect import get_db

BUCKET = "fs"
KIND_EBOOK = "ebook"
KIND_COVER = "cover"


def _bucket():
    return gridfs.GridFSBucket(get_db(), bucket_name=BUCKET)


def _fs():
    return gridfs.GridFS(get_db(), collection=BUCKET)


def _md5(path: str) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload(local_path: str, isbn: str, kind: str, original_name: str | None = None) -> dict:
    """上传一个文件到 GridFS，返回文件 id 与校验信息。"""
    if kind not in (KIND_EBOOK, KIND_COVER):
        raise ValueError("kind 只能是 ebook 或 cover")
    name = original_name or os.path.basename(local_path)
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    bucket = _bucket()
    with open(local_path, "rb") as fh:
        file_id = bucket.upload_from_stream(
            name,
            fh,
            metadata={
                "isbn": isbn,
                "type": kind,
                "original_name": name,
                "content_type": content_type,
                "upload_date": datetime.now(timezone.utc),
                "bytes": os.path.getsize(local_path),
                "md5": _md5(local_path),
            },
        )
    log_action("upload", BUCKET, f"{isbn}/{name}", f"上传{ '电子书' if kind == KIND_EBOOK else '封面' }，{os.path.getsize(local_path)} 字节")
    return {"file_id": file_id, "filename": name, "bytes": os.path.getsize(local_path)}


def find_files(isbn: str | None = None, kind: str | None = None) -> list[dict]:
    query: dict = {}
    if isbn:
        query["metadata.isbn"] = isbn
    if kind:
        query["metadata.type"] = kind
    return list(get_db()[f"{BUCKET}.files"].find(query).sort("uploadDate", -1))


def list_files(kind: str | None = None) -> list[dict]:
    rows = []
    for doc in find_files(kind=kind):
        meta = doc.get("metadata", {})
        rows.append({
            "filename": doc.get("filename"),
            "isbn": meta.get("isbn", "-"),
            "type": meta.get("type", "-"),
            "bytes": doc.get("length"),
            "md5": (doc.get("md5") or meta.get("md5", "-"))[:12],
            "upload": doc.get("uploadDate"),
        })
    return rows


def download(file_id, dest_dir: str | None = None) -> tuple[str, dict]:
    """按 _id 下载，返回本地路径与文件文档。"""
    dest_dir = dest_dir or os.path.join(settings.export_dir, "downloads")
    os.makedirs(dest_dir, exist_ok=True)
    doc = get_db()[f"{BUCKET}.files"].find_one({"_id": file_id})
    if not doc:
        raise GridFSNoFileError(f"GridFS 中不存在文件 {file_id}")
    path = os.path.join(dest_dir, doc["filename"])
    with open(path, "wb") as fh:
        _bucket().download_to_stream(file_id, fh)
    log_action("download", BUCKET, doc["filename"], f"下载 {doc.get('length')} 字节")
    return path, doc


def download_by_title(title: str, kind: str = KIND_EBOOK) -> dict:
    """按书名查询并下载对应文件，最后做字节数与 MD5 校验。"""
    book = get_db()["books"].find_one(
        {"title": {"$regex": title.strip(), "$options": "i"}}, sort=[("borrow_count", -1)]
    )
    if not book:
        return {"ok": False, "reason": f"未找到书名包含「{title}」的图书"}
    files = find_files(isbn=book["isbn"], kind=kind)
    if not files:
        return {"ok": False, "reason": f"《{book['title']}》没有已上传的{ '电子书' if kind == KIND_EBOOK else '封面' }"}
    doc = files[0]
    path, _ = download(doc["_id"])
    size_ok = os.path.getsize(path) == doc.get("length")
    md5_ok = _md5(path) == (doc.get("md5") or doc.get("metadata", {}).get("md5"))
    return {
        "ok": size_ok and md5_ok,
        "book": book["title"],
        "isbn": book["isbn"],
        "path": path,
        "expected_bytes": doc.get("length"),
        "actual_bytes": os.path.getsize(path),
        "md5_match": md5_ok,
    }


def upload_manifest_files(data_dir: str, manifest: dict) -> list[dict]:
    """按 files_manifest.txt 一次性上传 3 本电子书 + 3 张封面。"""
    results = []
    for item in manifest.get("ebooks", []):
        results.append(upload(os.path.join(data_dir, "gridfs_files", item["filename"]),
                              item["related_isbn"], KIND_EBOOK, item["filename"]))
    for item in manifest.get("covers", []):
        results.append(upload(os.path.join(data_dir, "gridfs_files", item["filename"]),
                              item["related_isbn"], KIND_COVER, item["filename"]))
    return results


def stats() -> dict:
    db = get_db()
    return {
        "files": db[f"{BUCKET}.files"].count_documents({}),
        "chunks": db[f"{BUCKET}.chunks"].count_documents({}),
        "total_bytes": sum(d.get("length", 0) for d in db[f"{BUCKET}.files"].find({}, {"length": 1})),
    }
