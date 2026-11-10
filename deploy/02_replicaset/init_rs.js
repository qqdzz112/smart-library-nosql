// 任务五：初始化三节点副本集 rs0（在 192.168.121.128:27101 上执行）
// mongosh --port 27101 --quiet init_rs.js
const cfg = {
  _id: "rs0",
  members: [
    { _id: 0, host: "192.168.121.128:27101", priority: 2 },   // 期望成为主节点
    { _id: 1, host: "192.168.121.129:27102", priority: 1 },
    { _id: 2, host: "192.168.121.130:27103", priority: 1 }
  ]
};

try {
  const r = rs.initiate(cfg);
  print("rs.initiate =>", JSON.stringify(r));
} catch (e) {
  print("rs.initiate 失败（可能已初始化）：" + e);
}

// 等待选举完成（最多 30 秒）
for (let i = 0; i < 30; i++) {
  sleep(1000);
  const s = rs.status();
  const primary = s.members.filter(m => m.stateStr === "PRIMARY");
  if (primary.length === 1) {
    print("选举完成，耗时约 " + (i + 1) + " 秒");
    break;
  }
}

const st = rs.status();
print("\n副本集名称: " + st.set + "   成员数: " + st.members.length);
print("成员明细:");
st.members.forEach(m => {
  print(`  ${m._id}  ${m.name.padEnd(26)} ${m.stateStr.padEnd(10)} health=${m.health}`);
});
const h = db.hello();
print("\n当前连接节点: " + h.me + "  是否主节点: " + h.isWritablePrimary + "  setName: " + h.setName);
