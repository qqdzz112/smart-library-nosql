// 任务六：打印 borrow_logs 的 chunk 范围与所在分片（mongos 上以 cluster_admin 执行）
const ns = "library.borrow_logs";
const chunks = db.getSiblingDB("config").chunks.find({ ns: ns }).sort({ min: 1 }).toArray();
print("chunk 数: " + chunks.length);
chunks.forEach(c => {
  print("  " + c.shard + "  min=" + JSON.stringify(c.min) + "  max=" + JSON.stringify(c.max));
});

const coll = db.getSiblingDB("library").borrow_logs;
print("reader_card 最小/最大/去重数:");
const agg = coll.aggregate([
  { $group: { _id: null, min: { $min: "$reader_card" }, max: { $max: "$reader_card" },
              readers: { $addToSet: "$reader_card" } } }
]).toArray()[0];
print("  min=" + agg.min + " max=" + agg.max + " 不同读者=" + agg.readers.length);

print("按 reader_card 前缀分组的文档数（前 8 个读者）:");
const perReader = coll.aggregate([
  { $group: { _id: "$reader_card", n: { $sum: 1 } } },
  { $sort: { _id: 1 } }, { $limit: 8 }
]).toArray();
perReader.forEach(r => print("  " + r._id + " -> " + r.n));
