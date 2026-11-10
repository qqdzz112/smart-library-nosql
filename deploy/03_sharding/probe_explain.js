// 探测 mongos 上 explain 输出的结构（用于修 verify_shard.js 的"涉及分片"字段）
const coll = db.getSiblingDB("library").borrow_logs;
const ex = coll.find({ status: "已归还" }).explain("executionStats");
print("顶层 keys: " + Object.keys(ex).join(", "));
if (ex.queryPlanner) print("queryPlanner keys: " + Object.keys(ex.queryPlanner).join(", "));
if (ex.queryPlanner && ex.queryPlanner.winningPlan)
  print("winningPlan keys: " + Object.keys(ex.queryPlanner.winningPlan).join(", "));
if (ex.executionStats) print("executionStats keys: " + Object.keys(ex.executionStats).join(", "));
if (ex.shards) print("shards: " + Object.keys(ex.shards).join(", "));
if (ex.queryPlanner && ex.queryPlanner.winningPlan && ex.queryPlanner.winningPlan.shards)
  print("winningPlan.shards: " + JSON.stringify(ex.queryPlanner.winningPlan.shards));
