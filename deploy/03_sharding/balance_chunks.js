// 任务六：把两个 chunk 分别落到两个分片（mongos 上以 cluster_admin 执行）
// 分片键 {reader_card:1, borrow_date:1}，split 点 R20240016；数据为 R20240001..R20240030 各 100 条。
const ns = "library.borrow_logs";
const LOWER = { reader_card: "R20240001", borrow_date: ISODate("1970-01-01T00:00:00Z") };
const UPPER = { reader_card: "R20240016", borrow_date: ISODate("1970-01-01T00:00:00Z") };

function tryMove(key, to, label) {
  try {
    const r = sh.moveChunk(ns, key, to);
    print(label + " -> " + to + "  ok=" + r.ok + "  millis=" + r.millis);
  } catch (e) {
    print(label + " 移动失败（可能已在该分片）：" + e.message);
  }
}

tryMove(LOWER, "shard1", "上半区 chunk(min..R20240016)");
tryMove(UPPER, "shard2", "下半区 chunk(R20240016..max)");

print("\n--- 最终分布 ---");
printjson(db.getSiblingDB("library").borrow_logs.getShardDistribution());
