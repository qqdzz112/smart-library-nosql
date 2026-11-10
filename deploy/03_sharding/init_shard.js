// 任务六：把两个分片加入集群、开启库分片、对 borrow_logs 分片（在 mongos 上执行）
// mongosh "mongodb://cluster_admin:Cluster%402026@127.0.0.1:27400/admin?authSource=admin" --quiet init_shard.js
// 分片是单节点副本集，addShard 必须用「副本集名/主机:端口」格式
const SHARDS = ["shard1/192.168.121.129:27301", "shard2/192.168.121.130:27302"];

SHARDS.forEach(addr => {
  try {
    const r = sh.addShard(addr);
    print("addShard " + addr + " => " + JSON.stringify(r));
  } catch (e) {
    print("addShard " + addr + " 失败（可能已存在）：" + e);
  }
});

printjson(db.adminCommand({ listShards: 1 }).shards.map(s => ({ _id: s._id, host: s.host })));

sh.enableSharding("library");
print("已对 library 开启分片");

// 分片键：{reader_card: 1, borrow_date: 1}（复合键，基数=读者数×日期数，且能支撑"按读者查借阅历史"定向查询）
const r = sh.shardCollection("library.borrow_logs", { reader_card: 1, borrow_date: 1 });
print("shardCollection => " + JSON.stringify(r));

const st = sh.status();
print("\n分片集合: " + JSON.stringify(st.databases.filter(d => d._id === "library")));
print("分片列表: " + st.shards.map(s => s._id + "@" + s.host).join("  "));
