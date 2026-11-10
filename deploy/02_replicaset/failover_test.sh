#!/usr/bin/env bash
# 任务五：读偏好演示 + 主节点故障转移计时（在 nosql01 执行）
set -u
cd "$HOME/final/app"
RS_URI="mongodb://lib_reader:Read%402026@192.168.121.128:27101,192.168.121.129:27102,192.168.121.130:27103/library?authSource=library&replicaSet=rs0"

echo "############ 1. 读取偏好演示（当前主节点正常） ############"
LIB_DB_URI="$RS_URI" LIB_DB_REPLICA_SET=rs0 python3 scripts/read_pref_demo.py

echo
echo "############ 2. 转移前状态 ############"
mongosh "mongodb://cluster_admin:Cluster%402026@192.168.121.128:27101/admin?authSource=admin" --quiet \
  --file deploy/02_replicaset/check_rs.js

echo
echo "############ 3. 停止主节点 rs1（192.168.121.128:27101） ############"
PID=$(cat "$HOME/final/rs1/mongod.pid")
T0=$(date +%s%N)
kill -TERM "$PID"
echo "已向 pid=$PID 发送 SIGTERM，计时开始：$(date '+%H:%M:%S.%3N')"

NEWPRIMARY=""
for i in $(seq 1 120); do
  sleep 0.5
  OUT=$(mongosh --quiet --port 27102 --eval 'print(db.hello().isWritablePrimary)' 2>/dev/null | tail -1)
  if [ "$OUT" = "true" ]; then
    T1=$(date +%s%N)
    EL=$(( (T1 - T0) / 1000000 ))
    echo "检测到新主节点出现，用时 ${EL} ms（约 $((EL/1000)) 秒）"
    NEWPRIMARY=1
    break
  fi
done
[ -z "$NEWPRIMARY" ] && echo "!! 60 秒内未选出新主节点，请检查"

echo
echo "############ 4. 故障期间的应用读写表现 ############"
echo "-- 4.1 readPreference=primary（主不可用，预期失败） --"
LIB_DB_URI="$RS_URI" LIB_DB_REPLICA_SET=rs0 python3 - <<'PY'
import os, sys
sys.path.insert(0, os.getcwd())
from pymongo import MongoClient, ReadPreference
from pymongo.errors import ServerSelectionTimeoutError
uri = os.environ["LIB_DB_URI"]
try:
    c = MongoClient(uri, read_preference=ReadPreference.PRIMARY, serverSelectionTimeoutMS=3000, replicaSet="rs0")
    print("  读到:", c.library.books.find_one({}, {"title": 1})["title"])
except ServerSelectionTimeoutError as e:
    print("  失败（符合预期）:", str(e).splitlines()[0][:110])
PY

echo "-- 4.2 readPreference=secondaryPreferred（预期成功读从节点） --"
LIB_DB_URI="$RS_URI" LIB_DB_REPLICA_SET=rs0 python3 - <<'PY'
import os, sys
sys.path.insert(0, os.getcwd())
from pymongo import MongoClient, ReadPreference
uri = os.environ["LIB_DB_URI"]
c = MongoClient(uri, read_preference=ReadPreference.SECONDARY_PREFERRED, serverSelectionTimeoutMS=3000, replicaSet="rs0")
print("  读到:", c.library.books.find_one({}, {"title": 1})["title"],
      "| 命中:", c.admin.command("hello")["me"])
PY

echo "-- 4.3 写入（无主期间预期失败） --"
LIB_DB_URI="mongodb://lib_writer:Write%402026@192.168.121.128:27101,192.168.121.129:27102,192.168.121.130:27103/library?authSource=library&replicaSet=rs0&retryWrites=false&serverSelectionTimeoutMS=3000" python3 - <<'PY'
import os, sys
sys.path.insert(0, os.getcwd())
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
c = MongoClient(os.environ["LIB_DB_URI"])
try:
    c.library.books.update_one({"isbn": "9787115428028"}, {"$set": {"stock": 15}})
    print("  写入成功（不应发生）")
except ServerSelectionTimeoutError as e:
    print("  写入失败（符合预期）:", str(e).splitlines()[0][:110])
PY

echo
echo "############ 5. 新主节点状态 ############"
mongosh --quiet --port 27102 --eval 'const h=db.hello(); print("新主: "+h.me+" setName="+h.setName)' 2>/dev/null
mongosh --quiet "mongodb://cluster_admin:Cluster%402026@192.168.121.129:27102/admin?authSource=admin" \
  --file deploy/02_replicaset/check_rs.js

echo
echo "############ 6. 重启原主节点，观察重新加入 ############"
mongod -f "$HOME/final/conf/rs1.conf" >/dev/null 2>&1
for i in $(seq 1 60); do
  sleep 1
  ST=$(mongosh --quiet --port 27101 --eval 'print(db.hello().isWritablePrimary + "|" + (db.hello().secondary ? "secondary" : "other"))' 2>/dev/null | tail -1)
  case "$ST" in
    *secondary*) echo "rs1 已重新加入并成为从节点（约 ${i} 秒）: $ST"; break ;;
  esac
done

mongosh "mongodb://cluster_admin:Cluster%402026@192.168.121.128:27101/admin?authSource=admin" --quiet \
  --file deploy/02_replicaset/check_rs.js
