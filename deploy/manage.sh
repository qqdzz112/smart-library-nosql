#!/usr/bin/env bash
# 启动/停止各角色的 mongod 与 mongos（按节点角色）
# 用法： bash manage.sh <node:01|02|03> <start|stop|status> <角色...>
#   role: standalone | rs | cfg | shard1 | shard2 | mongos
set -u
NODE="${1:?node}"; ACTION="${2:?action}"; shift 2 || true
BASE="${HOME}/final"
KEYFILE="${BASE}/secrets/keyfile"

start_one() {
  local conf="${BASE}/conf/$1.conf"
  if [ ! -f "$conf" ]; then echo "  缺少配置 $conf"; return 1; fi
  if pgrep -f "mongod -f ${conf}" > /dev/null 2>&1; then echo "  $1 已在运行"; return 0; fi
  mongod -f "$conf" && echo "  $1 启动成功 (端口 $(grep -oP 'port: \K[0-9]+' "$conf"))"
}

stop_one() {
  local name="$1"
  local pidfile="${BASE}/${name}/mongod.pid"
  if [ -f "$pidfile" ]; then
    kill "$(cat "$pidfile")" 2>/dev/null && echo "  已发送停止信号给 $name (pid $(cat "$pidfile"))"
  else
    echo "  $name 未运行（无 pid 文件）"
  fi
}

status_one() {
  local name="$1"; local pidfile="${BASE}/${name}/mongod.pid"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "  $name 运行中 pid=$(cat "$pidfile") 端口=$(grep -oP 'port: \K[0-9]+' "${BASE}/conf/${name}.conf" 2>/dev/null)"
  else
    echo "  $name 未运行"
  fi
}

for role in "$@"; do
  case "$ACTION" in
    start)
      case "$role" in
        mongos) mongos -f "${BASE}/conf/mongos.conf" && echo "  mongos 启动成功 (27400)" ;;
        *) start_one "$role" ;;
      esac ;;
    stop) stop_one "$role" ;;
    status) status_one "$role" ;;
  esac
done
