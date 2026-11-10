#!/usr/bin/env bash
# 任务六：启动 mongos、加入分片、开启分片、预分片（在 nosql01 执行）
set -u
cd "$HOME/final/app"
ADMIN='mongodb://cluster_admin:Cluster%402026@127.0.0.1:27400/admin?authSource=admin'

echo "== 1. 启动 mongos（127.0.0.1:27400 / 0.0.0.0:27400） =="
if pgrep -f 'final/conf/mongos.conf' >/dev/null; then
  echo "   mongos 已在运行"
else
  ~/final/bin/mongos -f "$HOME/final/conf/mongos.conf" && echo "   mongos 已启动"
fi
for i in $(seq 1 30); do
  mongosh --quiet --port 27400 --eval '1' >/dev/null 2>&1 && { echo "   路由端口已就绪（${i}s）"; break; }
  sleep 1
done

echo "== 2. 加入分片 + 开启库分片 + borrow_logs 分片键 =="
mongosh "$ADMIN" --quiet --file deploy/03_sharding/init_shard.js

echo
echo "== 3. 预分片（splitAt + moveChunk） =="
mongosh "$ADMIN" --quiet --file deploy/03_sharding/distribute_chunks.js

echo
echo "== 4. 集群拓扑 =="
mongosh "$ADMIN" --quiet --eval '
const s = db.adminCommand({ listShards: 1 });
print("分片数: " + s.shards.length);
s.shards.forEach(x => print("  " + x._id + " -> " + x.host));
const d = db.getSiblingDB("library").getCollectionNames();
print("library 集合: " + JSON.stringify(d));
'
