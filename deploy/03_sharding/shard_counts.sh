#!/usr/bin/env bash
# 任务六：直连两个分片，核对本地集合文档数（验证数据确实分布在两个分片上）
set -u
cd "$HOME/final/app"
J=deploy/03_sharding/count_local.js

echo "== shard1 (192.168.121.129:27301) =="
mongosh "mongodb://lib_admin:Admin%402026@192.168.121.129:27301/library?authSource=library&directConnection=true" --quiet --file "$J"
echo
echo "== shard2 (192.168.121.130:27302) =="
mongosh "mongodb://lib_admin:Admin%402026@192.168.121.130:27302/library?authSource=library&directConnection=true" --quiet --file "$J"
echo
echo "== 通过 mongos 汇总 =="
mongosh "mongodb://lib_admin:Admin%402026@127.0.0.1:27400/library?authSource=library" --quiet --file "$J"
