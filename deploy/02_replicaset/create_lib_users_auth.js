// 任务五：用 cluster_admin 认证后补建 library 库的业务账号
const lib = db.getSiblingDB("library");
// 口令一律从环境变量读取，仓库中不保存任何明文
const P = (key) => {
  const value = process.env[key] || "";
  if (!value) print("  ! 缺少环境变量 " + key + "（示例：export " + key + "='<你的密码>'）");
  return value;
};

const USERS = [
  ["lib_reader", P("LIB_PWD_READONLY"), [{ role: "read", db: "library" }], "只读账号"],
  ["lib_writer", P("LIB_PWD_READWRITE"), [{ role: "readWrite", db: "library" }], "读写账号"],
  ["lib_admin", P("LIB_PWD_ADMIN"), [{ role: "dbAdmin", db: "library" }, { role: "readWrite", db: "library" },
                               { role: "userAdmin", db: "library" }], "管理账号"],
];
USERS.forEach(([name, pwd, roles, desc]) => {
  if (!pwd) {
    print("  - 账号 " + name + " 跳过：口令环境变量未设置");
    return;
  }
  try {
    lib.createUser({ user: name, pwd: pwd, roles: roles });
    print("  + 账号 " + name + " 创建成功  (" + desc + ")");
  } catch (e) {
    print("  - 账号 " + name + " 跳过: " + e.codeName);
  }
});
print("\nlibrary 库用户: " + lib.getUsers().users.map(u => u.user + "[" + u.roles.map(r => r.role).join("/") + "]").join(", "));
