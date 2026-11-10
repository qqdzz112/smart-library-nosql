#!/usr/bin/env bash
# 任务六：导入后重新开启分片并均衡（--drop 会重建集合，需重新 shardCollection）
set -u
cd "$HOME/final/app"
ADMIN='mongodb://cluster_admin:Cluster%402026@127.0.0.1:27400/admin?authSource=admin'

echo "== 1. 补分片键索引 + 开启分片 =="
mongosh "$ADMIN" --quiet --file deploy/03_sharding/shard_collection.js

echo
echo "== 2. 预分片：splitAt + moveChunk =="
mongosh "$ADMIN" --quiet --file deploy/03_sharding/distribute_chunks.js

echo
echo "== 3. 分片分布 =="
mongosh "$ADMIN" --quiet --file deploy/03_sharding/check_distribution.js
