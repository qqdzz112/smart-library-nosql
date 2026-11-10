// 任务五：在副本集主节点上建账号（首次建号走 localhost exception，需在无认证状态下执行）
// mongosh --port 27101 --quiet create_rs_users.js
const admin = db.getSiblingDB("admin");
const lib = db.getSiblingDB("library");

// 口令一律从环境变量读取，仓库中不保存任何明文
const P = (key) => {
  const value = process.env[key] || "";
  if (!value) print("  ! 缺少环境变量 " + key + "（示例：export " + key + "='<你的密码>'）");
  return value;
};

const USERS = [
  ["cluster_admin", P("LIB_PWD_CLUSTER"), [{ role: "root", db: "admin" }], "集群管理账号"],
  ["lib_reader", P("LIB_PWD_READONLY"), [{ role: "read", db: "library" }], "只读账号"],
  ["lib_writer", P("LIB_PWD_READWRITE"), [{ role: "readWrite", db: "library" }], "读写账号"],
  ["lib_admin", P("LIB_PWD_ADMIN"), [{ role: "dbAdmin", db: "library" }, { role: "readWrite", db: "library" },
                               { role: "userAdmin", db: "library" }], "管理账号"],
];

USERS.forEach(([name, pwd, roles, desc]) => {
  const target = name === "cluster_admin" ? admin : lib;
  if (!pwd) {
    print("  - 账号 " + name + " 跳过：口令环境变量未设置");
    return;
  }
  try {
    target.createUser({ user: name, pwd: pwd, roles: roles });
    print("  + 账号 " + name + " 创建成功  (" + desc + ")");
  } catch (e) {
    print("  - 账号 " + name + " 已存在或失败: " + e.codeName);
  }
});

print("\nadmin 库用户: " + admin.getUsers().users.map(u => u.user).join(", "));
print("library 库用户: " + lib.getUsers().users.map(u => u.user).join(", "));
