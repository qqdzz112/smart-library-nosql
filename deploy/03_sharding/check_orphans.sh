#!/usr/bin/env bash
# 任务六：检查 shard2 上待清理的孤儿文档（rangeDeletions）与清理进度
set -u
echo "== 待清理区间 =="
mongosh "mongodb://cluster_admin:Cluster%402026@127.0.0.1:27302/admin?authSource=admin&directConnection=true" --quiet --eval '
const rd = db.getSiblingDB("config").rangeDeletions.find().toArray();
print("pending rangeDeletions: " + rd.length);
rd.forEach(r => print("  " + JSON.stringify(r)));
'
echo
echo "== mongod 日志中的 range deleter / orphan 记录（最近 20 行） =="
grep -iE "range deleter|orphan|RangeDeletion" "$HOME/final/shard2/log/mongod.log" | tail -n 20
