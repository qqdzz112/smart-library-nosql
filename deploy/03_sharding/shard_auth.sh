#!/usr/bin/env bash
# 任务六：分片集群访问控制验证（mongos 127.0.0.1:27400）
set -u
cd "$HOME/final/app"
J=deploy/03_sharding/shard_auth_check.js
for pair in "lib_reader:Read%402026" "lib_writer:Write%402026" "lib_admin:Admin%402026"; do
  user="${pair%%:*}"; pwd="${pair##*:}"
  LIB_ROLE="$user" mongosh "mongodb://${user}:${pwd}@127.0.0.1:27400/library?authSource=library" --quiet --file "$J"
  echo
done
