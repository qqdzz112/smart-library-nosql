// 任务三：只读账号越权验证（lib_reader 只有 read 权限）
// mongosh "mongodb://lib_reader:Read%402026@127.0.0.1:27017/library?authSource=library" --quiet verify_reader.js
print("当前账号: " + db.runCommand({ connectionStatus: 1 }).authInfo.authenticatedUsers.map(u => u.user).join(","));
print("可读: books 文档数 = " + db.books.countDocuments({}));

try {
  db.books.insertOne({ isbn: "TEST-VIOLATE", title: "越权写入测试" });
  print("!! 异常：只读账号写入成功（不应发生）");
} catch (e) {
  print("写入被拒绝: " + e.codeName + " / " + e.code + "  " + e.errmsg.split("\n")[0]);
}

// 删除目标故意选一个不存在的 ISBN：即使脚本被误用高权限账号执行，也不会破坏真实馆藏
try {
  db.books.deleteOne({ isbn: "TEST-VIOLATE" });
  print("!! 异常：只读账号删除成功（不应发生）");
} catch (e) {
  print("删除被拒绝: " + e.codeName + " / " + e.code);
}
db.books.deleteOne({ isbn: "TEST-VIOLATE" });
