#!/usr/bin/env bash
# 任务六：通过 mongos 导入三份数据，并验证分片分布
set -u
cd "$HOME/final/app"
LIB='mongodb://lib_admin:Admin%402026@127.0.0.1:27400/library?authSource=library'
ADMIN='mongodb://cluster_admin:Cluster%402026@127.0.0.1:27400/admin?authSource=admin'

echo "== 1. 通过 mongos 导入（--drop 重建） =="
LIB_DB_URI="$LIB" python3 scripts/init_db.py --data-dir data/raw --drop

echo
echo "== 2. 数据量核对（mongos 视角） =="
mongosh "$LIB" --quiet --eval '
const c = { books: db.books.countDocuments({}), readers: db.readers.countDocuments({}),
            borrow_logs: db.borrow_logs.countDocuments({}) };
printjson(c);
'

echo
echo "== 3. 分片分布（数据是否真的落到两个分片） =="
mongosh "$ADMIN" --quiet --eval '
const st = db.adminCommand({ listShards: 1 });
print("分片: " + st.shards.map(s => s._id + "@" + s.host).join(", "));
const coll = db.getSiblingDB("library").borrow_logs;
printjson(coll.getShardDistribution());
const chunks = db.getSiblingDB("config").chunks.aggregate([
  { $match: { "ns": "library.borrow_logs" } },
  { $group: { _id: "$shard", n: { $sum: 1 } } }
]).toArray();
print("chunk 数量按分片: " + JSON.stringify(chunks));
'

echo
echo "== 4. 定向查询 vs 跨分片查询 =="
mongosh "$ADMIN" --quiet --file deploy/03_sharding/verify_shard.js
