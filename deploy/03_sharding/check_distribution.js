// 任务六：查看 borrow_logs 在分片间的分布（在 mongos 上以 cluster_admin 执行）
const ns = "library.borrow_logs";
const coll = db.getSiblingDB("library").borrow_logs;

print("总数: " + coll.countDocuments({}));
const chunks = db.getSiblingDB("config").chunks.aggregate([
  { $match: { ns: ns } },
  { $group: { _id: "$shard", chunks: { $sum: 1 } } }
]).toArray();
print("chunk 分布: " + JSON.stringify(chunks));

const st = db.adminCommand({ listShards: 1 });
st.shards.forEach(s => {
  const host = s.host.replace(/^[^/]+\//, "").split(",")[0];
  print("分片 " + s._id + " (" + host + ")");
});
printjson(coll.getShardDistribution());
