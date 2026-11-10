// 任务六：初始化配置服务器副本集 cfgRS（在 192.168.121.128:27201 执行）
// mongosh --port 27201 --quiet init_cfg.js
try {
  const r = rs.initiate({
    _id: "cfgRS",
    configsvr: true,
    members: [{ _id: 0, host: "192.168.121.128:27201" }]
  });
  print("rs.initiate(cfgRS) =>", JSON.stringify(r));
} catch (e) {
  print("配置服务器初始化失败（可能已初始化）：" + e);
}
for (let i = 0; i < 20; i++) {
  sleep(1000);
  if (rs.status().members.some(m => m.stateStr === "PRIMARY")) { print("cfgRS 就绪，用时约 " + (i + 1) + " 秒"); break; }
}
printjson(rs.status().members.map(m => ({ name: m.name, state: m.stateStr })));
