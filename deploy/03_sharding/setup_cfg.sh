#!/usr/bin/env bash
# 任务六：配置服务器（cfgRS，nosql01:27201）初始化 + 首个管理员
set -u
cd "$HOME/final/app"
PORT=27201

echo "== 1. 启动配置服务器 =="
if pgrep -f 'final/conf/cfg.conf' >/dev/null; then
  echo "   cfg 已在运行"
else
  mongod -f "$HOME/final/conf/cfg.conf" && echo "   cfg 已启动"
fi
for i in $(seq 1 30); do
  mongosh --quiet --port $PORT --eval '1' >/dev/null 2>&1 && { echo "   端口已就绪（${i}s）"; break; }
  sleep 1
done

echo "== 2. 初始化配置服务器副本集 cfgRS =="
mongosh --quiet --port $PORT --eval \
  'try { printjson(rs.initiate({_id:"cfgRS", configsvr:true, members:[{_id:0, host:"192.168.121.128:27201"}]})) } catch(e) { print("initiate: " + e.codeName) }'

for i in $(seq 1 60); do
  P=$(mongosh --quiet --port $PORT --eval 'print(db.hello().isWritablePrimary)' 2>/dev/null | tail -1)
  [ "$P" = "true" ] && { echo "   cfgRS 主节点就绪（${i}s）"; break; }
  sleep 1
done

echo "== 3. 建集群管理员（localhost exception，只对第一个用户生效） =="
# 口令由环境变量注入，仓库中不保存明文
: "${LIB_PWD_CLUSTER:?请先设置 LIB_PWD_CLUSTER（集群管理员口令）}"
mongosh --quiet --port $PORT --eval \
  "const a = db.getSiblingDB('admin'); try { a.createUser({user:'cluster_admin', pwd:'${LIB_PWD_CLUSTER}', roles:[{role:'root', db:'admin'}]}); print('   cluster_admin 创建成功') } catch(e) { print('   createUser: ' + e.codeName) }"

echo "== 4. 认证后补建 library 业务账号 =="
mongosh "mongodb://cluster_admin:$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote_plus(sys.argv[1]))" "$LIB_PWD_CLUSTER")@127.0.0.1:${PORT}/admin?authSource=admin" --quiet \
  --file deploy/02_replicaset/create_lib_users_auth.js

echo "== 5. 状态 =="
mongosh "mongodb://cluster_admin:$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote_plus(sys.argv[1]))" "$LIB_PWD_CLUSTER")@127.0.0.1:${PORT}/admin?authSource=admin" --quiet \
  --eval 'const s = rs.status(); print("cfgRS 成员: " + s.members.map(m => m.name + "=" + m.stateStr).join(", "))'
