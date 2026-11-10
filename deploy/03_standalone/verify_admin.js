// 任务三：管理账号验证（lib_admin 有 dbAdmin + userAdmin + readWrite）
// mongosh "mongodb://lib_admin:Admin%402026@127.0.0.1:27017/library?authSource=library" --quiet verify_admin.js
print("当前账号 roles: " + JSON.stringify(db.runCommand({ connectionStatus: 1 }).authInfo.authenticatedUserRoles));
const idx = db.books.createIndex({ _verify_tmp: 1 });
print("可建索引: " + idx);
print("删除临时索引: " + JSON.stringify(db.books.dropIndex("_verify_tmp_1")));
print("集合统计: " + JSON.stringify(db.runCommand({ dbStats: 1 }).collections));
print("索引清单:");
db.books.getIndexes().forEach(i => print("  " + i.name + "  " + JSON.stringify(i.key)));
