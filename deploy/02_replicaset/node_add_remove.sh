#!/usr/bin/env bash
cd "$HOME/final/app"
ADMIN='mongodb://cluster_admin:Cluster%402026@192.168.121.128:27101,192.168.121.129:27102,192.168.121.130:27103/admin?authSource=admin&replicaSet=rs0'

echo "== 1. 演练前 =="
mongosh "$ADMIN" --quiet --file deploy/02_replicaset/check_rs.js

echo
echo "== 2. rs.remove 移除第三节点 192.168.121.130:27103 =="
mongosh "$ADMIN" --quiet --eval 'const r = rs.remove("192.168.121.130:27103"); printjson({ok: r.ok});'
sleep 2
mongosh "$ADMIN" --quiet --file deploy/02_replicaset/check_rs.js

echo
echo "== 3. rs.add 重新加入 192.168.121.130:27103 =="
mongosh "$ADMIN" --quiet --eval 'const r = rs.add("192.168.121.130:27103"); printjson({ok: r.ok});'

echo "== 4. 等待新成员完成初始同步 =="
for i in $(seq 1 90); do
  S=$(mongosh "$ADMIN" --quiet --eval 'const m = rs.status().members.find(x => x.name === "192.168.121.130:27103"); print(m ? m.stateStr : "MISSING")' 2>/dev/null | tail -1)
  echo "   ${i}s: 192.168.121.130:27103 = $S"
  [ "$S" = "SECONDARY" ] && break
  sleep 2
done

echo
echo "== 5. 演练后最终状态 =="
mongosh "$ADMIN" --quiet --file deploy/02_replicaset/check_rs.js
echo
echo "== 6. 新加入成员的库表数据核对 =="
mongosh "mongodb://lib_reader:Read%402026@192.168.121.130:27103/library?authSource=library&directConnection=true" --quiet \
  --eval 'print("books="+db.books.countDocuments({})+" readers="+db.readers.countDocuments({})+" borrow_logs="+db.borrow_logs.countDocuments({}))'
