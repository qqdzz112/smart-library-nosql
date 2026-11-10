#!/usr/bin/env bash
# 任务五证据采集（副本集 rs0，nosql01 上执行）
set -u
cd "$HOME/final/app"
OUT="$HOME/final/evidence"
mkdir -p "$OUT"

ADMIN='mongodb://cluster_admin:Cluster%402026@192.168.121.128:27101/admin?authSource=admin'
LIB='mongodb://lib_admin:Admin%402026@192.168.121.128:27101/library?authSource=library&replicaSet=rs0'

echo "[1/3] 副本集状态"
mongosh "mongodb://cluster_admin:Cluster%402026@192.168.121.128:27101/admin?authSource=admin&directConnection=true" \
  --quiet --file deploy/02_replicaset/check_rs.js > "$OUT/05_rs_status.txt" 2>&1

echo "[2/3] 读取偏好演示"
LIB_DB_URI="$LIB" python3 scripts/read_pref_demo.py > "$OUT/05_read_pref.txt" 2>&1

echo "[3/3] 副本集数据核对"
mongosh "$LIB" --quiet --eval 'print(JSON.stringify({books: db.books.countDocuments({}), readers: db.readers.countDocuments({}), borrow_logs: db.borrow_logs.countDocuments({})}))' \
  > "$OUT/05_rs_counts.txt" 2>&1

ls -l "$OUT"
