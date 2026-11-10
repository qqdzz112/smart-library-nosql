// 任务六：验证分片生效 + 定向查询 vs 跨分片查询对比（在 mongos 上执行）
// mongosh "mongodb://cluster_admin:Cluster%402026@127.0.0.1:27400/admin?authSource=admin" --quiet verify_shard.js
const lib = db.getSiblingDB("library");
const coll = lib.borrow_logs;

function shardsOf(ex) {
  const wp = ex.queryPlanner && ex.queryPlanner.winningPlan;
  const arr = (wp && wp.shards) || [];
  return arr.map(s => s.shardName);
}

print("=== 1. 分片拓扑 ===");
printjson(db.adminCommand({ listShards: 1 }).shards.map(s => ({ _id: s._id, host: s.host })));

print("\n=== 2. 数据在分片间的分布 ===");
printjson(lib.borrow_logs.getShardDistribution());

print("\n=== 3. 定向查询（含分片键前缀 reader_card，只应命中 1 个分片） ===");
const targeted = { reader_card: "R20240005", borrow_date: { $gte: ISODate("2023-01-01T00:00:00Z") } };
let ex = coll.find(targeted).explain("executionStats");
print("涉及分片: [" + shardsOf(ex).join(", ") + "]   返回文档: " + ex.executionStats.nReturned +
      "   检查文档: " + ex.executionStats.totalDocsExamined +
      "   耗时: " + ex.executionStats.executionTimeMillis + " ms");
let t0 = Date.now();
for (let i = 0; i < 20; i++) coll.find(targeted).toArray();
print("20 次平均耗时: " + ((Date.now() - t0) / 20).toFixed(2) + " ms");

print("\n=== 4. 跨分片查询（不含分片键，广播到所有分片） ===");
const scatter = { status: "已归还" };
ex = coll.find(scatter).explain("executionStats");
print("涉及分片: [" + shardsOf(ex).join(", ") + "]   返回文档: " + ex.executionStats.nReturned +
      "   检查文档: " + ex.executionStats.totalDocsExamined +
      "   耗时: " + ex.executionStats.executionTimeMillis + " ms");
t0 = Date.now();
for (let i = 0; i < 20; i++) coll.find(scatter).toArray();
print("20 次平均耗时: " + ((Date.now() - t0) / 20).toFixed(2) + " ms");

print("\n=== 5. 全局计数（mongos 汇总） ===");
print("borrow_logs 总数 = " + coll.countDocuments({}));
print("books = " + lib.books.countDocuments({}) + "   readers = " + lib.readers.countDocuments({}));
