// 任务六：对已存在的 borrow_logs 开启分片（在 mongos 上以 cluster_admin 执行）
const ns = "library.borrow_logs";
const KEY = { reader_card: 1, borrow_date: 1 };

const coll = db.getSiblingDB("library").borrow_logs;
print("现有索引:");
coll.getIndexes().forEach(i => print("  " + i.name + "  " + JSON.stringify(i.key)));

// 分片键必须有一个「键模式完全一致」的索引（字段与方向都要一致）。
// 现有 idx_reader_borrowdate 是 {reader_card:1, borrow_date:-1}，方向不同，不能复用。
const need = coll.getIndexes().some(i => {
  const k = Object.keys(i.key);
  return k.length === 2 && k[0] === "reader_card" && k[1] === "borrow_date" &&
         i.key.reader_card === 1 && i.key.borrow_date === 1;
});
if (!need) {
  print("补建分片键索引 idx_shard_reader_borrowdate ...");
  printjson(coll.createIndex(KEY, { name: "idx_shard_reader_borrowdate" }));
} else {
  print("分片键索引已存在");
}

print("shardCollection => " + JSON.stringify(sh.shardCollection(ns, KEY)));
