// 任务三：读写账号验证（lib_writer 有 readWrite）
// 说明：MongoDB 的 readWrite 内置角色本身包含 createIndex / dropIndex，
// 因此"读写账号不能建索引"是常见误解；真正越界的是建账号、删库、改副本集配置。
// mongosh "mongodb://lib_writer:Write%402026@127.0.0.1:27017/library?authSource=library" --quiet verify_writer.js
print("当前账号: " + db.runCommand({ connectionStatus: 1 }).authInfo.authenticatedUsers.map(u => u.user).join(","));
const r = db.books.updateOne({ isbn: "9787115428028" }, { $inc: { stock: 0 } });
print("可写: matched=" + r.matchedCount + " modified=" + r.modifiedCount);

print("建索引（readWrite 内置允许）: " + db.books.createIndex({ test_field: 1 }));
print("删除该索引: " + JSON.stringify(db.books.dropIndex("test_field_1")));

try {
  db.runCommand({ createUser: "hacker", pwd: "x", roles: [{ role: "readWrite", db: "library" }] });
  print("!! 异常：读写账号成功建账号（不应发生）");
} catch (e) {
  print("建账号被拒绝: " + e.codeName + " / " + e.code);
}

try {
  db.dropDatabase();
  print("!! 异常：读写账号成功删库（不应发生）");
} catch (e) {
  print("删库被拒绝: " + e.codeName + " / " + e.code);
}
