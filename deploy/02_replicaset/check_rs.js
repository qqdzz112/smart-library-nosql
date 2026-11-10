// 任务五：查看副本集状态（任意成员执行）
// mongosh --port 27102 --quiet check_rs.js
const st = rs.status();
print("副本集: " + st.set + "  成员数: " + st.members.length);
print("--------------------------------------------------------------------------------");
print("id  主机                        角色        健康   uptime(s)  复制延迟(optimeDate)");
print("--------------------------------------------------------------------------------");
const primary = st.members.find(m => m.stateStr === "PRIMARY");
st.members.forEach(m => {
  let lag = "-";
  if (primary && m.stateStr !== "PRIMARY" && m.optimeDate && primary.optimeDate) {
    lag = ((primary.optimeDate - m.optimeDate) / 1000).toFixed(0) + "s";
  }
  print(`${String(m._id).padEnd(3)} ${m.name.padEnd(27)} ${m.stateStr.padEnd(11)} ${String(m.health).padEnd(5)} ${String(m.uptime).padEnd(10)} ${lag}`);
});
const h = db.hello();
print("\n本次连接命中的节点: " + h.me + "  isWritablePrimary=" + h.isWritablePrimary);
print("读偏好: " + db.getMongo().getReadPrefMode() + "  主节点写入是否可用: " + h.isWritablePrimary);
