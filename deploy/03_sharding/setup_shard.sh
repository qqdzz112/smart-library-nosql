#!/usr/bin/env bash
# 任务六：分片节点初始化（单节点副本集，shardsvr）
# 用法： bash setup_shard.sh shard1|shard2
set -u
NAME="${1:?用法: setup_shard.sh shard1|shard2}"
cd "$HOME/final/app"
case "$NAME" in
  shard1) PORT=27301; IP=192.168.121.129 ;;
  shard2) PORT=27302; IP=192.168.121.130 ;;
  *) echo "未知分片: $NAME"; exit 1 ;;
esac

echo "== 1. 启动 $NAME（${IP}:${PORT}，clusterRole=shardsvr） =="
if pgrep -f "final/conf/${NAME}.conf" >/dev/null; then
  echo "   已在运行"
else
  mongod -f "$HOME/final/conf/${NAME}.conf" && echo "   已启动"
fi
for i in $(seq 1 30); do
  mongosh --quiet --port $PORT --eval '1' >/dev/null 2>&1 && { echo "   端口已就绪（${i}s）"; break; }
  sleep 1
done

echo "== 2. 初始化为单节点副本集 =="
mongosh --quiet --port $PORT --eval \
  "try { printjson(rs.initiate({_id:\"${NAME}\", members:[{_id:0, host:\"${IP}:${PORT}\"}]})) } catch(e) { print(\"initiate: \" + e.codeName) }"
for i in $(seq 1 60); do
  P=$(mongosh --quiet --port $PORT --eval 'print(db.hello().isWritablePrimary)' 2>/dev/null | tail -1)
  [ "$P" = "true" ] && { echo "   ${NAME} 主节点就绪（${i}s）"; break; }
  sleep 1
done

echo "== 3. 建集群管理员与业务账号 =="
# 口令由环境变量注入，仓库中不保存明文
: "${LIB_PWD_CLUSTER:?请先设置 LIB_PWD_CLUSTER（集群管理员口令）}"
mongosh --quiet --port $PORT --eval \
  "const a = db.getSiblingDB('admin'); try { a.createUser({user:'cluster_admin', pwd:'${LIB_PWD_CLUSTER}', roles:[{role:'root', db:'admin'}]}); print('   cluster_admin 创建成功') } catch(e) { print('   createUser: ' + e.codeName) }"
mongosh "mongodb://cluster_admin:$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote_plus(sys.argv[1]))" "$LIB_PWD_CLUSTER")@127.0.0.1:${PORT}/admin?authSource=admin" --quiet \
  --file deploy/02_replicaset/create_lib_users_auth.js

echo "== 4. 状态 =="
mongosh "mongodb://cluster_admin:$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote_plus(sys.argv[1]))" "$LIB_PWD_CLUSTER")@127.0.0.1:${PORT}/admin?authSource=admin" --quiet \
  --eval 'const s = rs.status(); print("成员: " + s.members.map(m => m.name + "=" + m.stateStr).join(", ")); print("数据目录大小: " + db.serverStatus().storageEngine.name)'
