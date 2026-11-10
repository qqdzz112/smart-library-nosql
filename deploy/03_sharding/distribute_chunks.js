// 任务六：预分片（在导入 3000 条之前执行）。
// 3000 条远小于默认 chunk 大小(128MB)，不预分片则全部落在主分片上，
// 因此按 reader_card 中点手动 split + moveChunk，保证两分片都承载数据。
// 在 mongos 上执行：mongosh "mongodb://cluster_admin:Cluster%402026@127.0.0.1:27400/admin" distribute_chunks.js
const ns = "library.borrow_logs";
const SPLIT_KEY = { reader_card: "R20240016", borrow_date: ISODate("1970-01-01T00:00:00Z") };

const shardIds = db.adminCommand({ listShards: 1 }).shards.map(s => s._id);
const target = shardIds[shardIds.length - 1]; // 后加入的分片（shard02）

try {
  print("splitAt " + JSON.stringify(SPLIT_KEY));
  sh.splitAt(ns, SPLIT_KEY);
} catch (e) {
  print("splitAt 失败（可能已分片过）：" + e);
}

try {
  print("moveChunk -> " + target);
  printjson(sh.moveChunk(ns, SPLIT_KEY, target));
} catch (e) {
  print("moveChunk 失败：" + e);
}

print("\n--- 当前 chunk 分布 ---");
sh.status();
print("\n--- 集合级分片分布（导入后数据量应两分片均有）---");
db.getSiblingDB("library").borrow_logs.getShardDistribution();
