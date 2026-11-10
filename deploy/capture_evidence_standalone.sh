#!/usr/bin/env bash
# 任务三/四证据采集（在 nosql03 单机实例上执行）
set -u
cd "$HOME/final/app"
export LIB_DB_URI="mongodb://lib_writer:Write%402026@127.0.0.1:27017/library?authSource=library"
OUT="$HOME/final/evidence"
mkdir -p "$OUT" docs/evidence

echo "[1/4] 数据校验"
python3 scripts/verify_data.py > "$OUT/03_verify_data.txt" 2>&1

echo "[2/4] 索引前后性能对比"
python3 scripts/perf_index.py > "$OUT/03_perf_index.txt" 2>&1

echo "[3/4] 11 项检索与统计"
python3 scripts/task3_demo.py > "$OUT/03_task3_demo.txt" 2>&1

echo "[4/4] GridFS 电子书存取校验"
LIB_DB_URI="$LIB_DB_URI" python3 scripts/gridfs_demo.py > "$OUT/03_gridfs.txt" 2>&1

ls -l "$OUT"
