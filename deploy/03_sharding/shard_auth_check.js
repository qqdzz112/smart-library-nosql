// 任务六：分片集群上的访问控制验证（在 mongos 上执行，不同账号跑同一段逻辑）
// mongosh "mongodb://lib_reader:Read%402026@127.0.0.1:27400/library?authSource=library" --quiet shard_auth_check.js
const role = (typeof process !== "undefined" && process.env.LIB_ROLE) || "unknown";
const coll = db.getSiblingDB("library").borrow_logs;

function attempt(label, fn) {
  try {
    const r = fn();
    print("  [允许] " + label + " -> " + JSON.stringify(r && r.result ? r.result : r));
    return { label: label, ok: true };
  } catch (e) {
    print("  [拒绝] " + label + " -> " + e.codeName + " / " + e.code);
    return { label: label, ok: false, code: e.code, codeName: e.codeName };
  }
}

print("=== 角色: " + role + " ===");
attempt("查询 borrow_logs", () => coll.findOne({ reader_card: "R20240005" }));
attempt("插入借阅日志", () => coll.insertOne({
  reader_card: "R20240030", book_isbn: "9787115428028",
  borrow_date: new Date("2025-12-31T09:00:00Z"), status: "借出"
}));
attempt("更新一条日志", () => coll.updateOne({ reader_card: "R20240005" }, { $set: { status: "逾期" } }));

print("=== 收尾：删除刚才插入的测试文档（仅管理/读写权限成功） ===");
attempt("删除测试文档", () => coll.deleteMany({ borrow_date: new Date("2025-12-31T09:00:00Z") }));
print("当前 borrowers 总数: " + coll.countDocuments({}));
