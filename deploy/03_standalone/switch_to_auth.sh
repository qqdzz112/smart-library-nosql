#!/usr/bin/env bash
# 任务三（nosql03）：切到认证模式并验证三个账号权限边界
set -e
cd "$HOME/final/app"
AUTH_URI_BASE="mongodb://%s:27017/library?authSource=library"

echo "=== 1. 停止无认证实例 ==="
mongosh --quiet --port 27017 --eval 'db.getSiblingDB("admin").shutdownServer({force:true})' 2>/dev/null || true
sleep 2

echo "=== 2. 以 standalone-auth.conf 启动（authorization: enabled） ==="
pgrep -f "standalone-auth.conf" >/dev/null || mongod -f "$HOME/final/conf/standalone-auth.conf"
sleep 3

echo
echo "=== 3. 未认证直接访问（应被拒绝） ==="
mongosh --quiet --port 27017 --eval 'db.books.countDocuments({})' 2>&1 | head -3 || true

echo
echo "=== 4. lib_reader 只读账号 ==="
mongosh "mongodb://lib_reader:Read%402026@127.0.0.1:27017/library?authSource=library" --quiet --file "$HOME/final/app/deploy/03_standalone/verify_reader.js"

echo
echo "=== 5. lib_writer 读写账号 ==="
mongosh "mongodb://lib_writer:Write%402026@127.0.0.1:27017/library?authSource=library" --quiet --file "$HOME/final/app/deploy/03_standalone/verify_writer.js"

echo
echo "=== 6. lib_admin 管理账号 ==="
mongosh "mongodb://lib_admin:Admin%402026@127.0.0.1:27017/library?authSource=library" --quiet --file "$HOME/final/app/deploy/03_standalone/verify_admin.js"
