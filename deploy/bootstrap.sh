#!/usr/bin/env bash
# 三节点部署引导：建目录、生成/校验 keyFile、渲染配置
# 用法（在 nosql01 上执行）：bash ~/final/app/deploy/bootstrap.sh 01|02|03
set -euo pipefail

NODE="${1:?用法: bootstrap.sh 01|02|03}"
BASE="$HOME/final"
APP="$BASE/app"
mkdir -p "$BASE"/{conf,logs,secrets}

# keyFile：三节点必须字节完全一致、权限 400，否则 mongod 直接拒绝启动
if [[ "$NODE" == "01" && ! -f "$BASE/secrets/keyfile" ]]; then
  openssl rand -base64 756 > "$BASE/secrets/keyfile"
  echo "[01] 已生成 keyFile ($(wc -c < "$BASE/secrets/keyfile") 字节)"
fi
if [[ -f "$BASE/secrets/keyfile" ]]; then
  chmod 400 "$BASE/secrets/keyfile"
else
  echo "警告：本机缺少 $BASE/secrets/keyfile，请从 nosql01 scp 过来后再启动 rs/cfg/shard 实例" >&2
fi

for d in standalone rs1 rs2 rs3 cfg shard1 shard2 mongos; do
  mkdir -p "$BASE/$d/data" "$BASE/$d/log"
done

bash "$APP/deploy/render_confs.sh" "$NODE"

echo "[$NODE] 目录与配置就绪：$BASE"
echo "如需放行端口（root 执行一次）:"
echo "  firewall-cmd --add-port=27017/tcp --add-port=27101-27103/tcp --add-port=27201/tcp --add-port=27301-27302/tcp --add-port=27400/tcp --permanent && firewall-cmd --reload"
