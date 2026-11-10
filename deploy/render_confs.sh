#!/usr/bin/env bash
# 按节点角色生成 MongoDB 配置文件（单机 / 副本集 / 分片集群）
# 用法： bash render_confs.sh 01|02|03
# 节点角色：01 = 副本集成员 rs1 + 配置服务器 cfg + 路由 mongos
#           02 = 副本集成员 rs2 + 分片 shard1
#           03 = 副本集成员 rs3 + 分片 shard2 + 单机实例
set -eu
NODE="${1:?用法: render_confs.sh 01|02|03}"
BASE="${HOME}/final"
CONF_DIR="${BASE}/conf"
KEYFILE="${BASE}/secrets/keyfile"
mkdir -p "${CONF_DIR}" "${BASE}/logs"

case "$NODE" in
  01) IP=192.168.121.128 ;;
  02) IP=192.168.121.129 ;;
  03) IP=192.168.121.130 ;;
  *) echo "未知节点: $NODE"; exit 1 ;;
esac

SEC_AUTH="security:
  keyFile: ${KEYFILE}
  authorization: enabled"

# render_conf 名称 端口 副本集名 集群角色 绑定地址 附加片段
render_conf() {
  local name="$1" port="$2" repl="$3" role="$4" bind="$5" extra="$6"
  local conf="${CONF_DIR}/${name}.conf"
  {
    if [[ "$name" != "mongos" ]]; then
      echo "storage:"
      echo "  dbPath: ${BASE}/${name}/data"
      echo "  wiredTiger:"
      echo "    engineConfig:"
      echo "      cacheSizeGB: 0.25"
    fi
    echo "systemLog:"
    echo "  destination: file"
    echo "  path: ${BASE}/${name}/log/mongod.log"
    echo "  logAppend: true"
    echo "net:"
    echo "  port: ${port}"
    echo "  bindIp: ${bind}"
    echo "processManagement:"
    echo "  fork: true"
    if [[ "$name" != "mongos" ]]; then
      echo "  pidFilePath: ${BASE}/${name}/mongod.pid"
    else
      echo "  pidFilePath: ${BASE}/${name}/mongos.pid"
    fi
    [[ -n "$repl" ]] && printf 'replication:\n  replSetName: %s\n' "$repl"
    [[ -n "$role" ]] && printf 'sharding:\n  clusterRole: %s\n' "$role"
    [[ -n "$extra" ]] && printf '%s\n' "$extra"
  } > "$conf"
  mkdir -p "${BASE}/${name}/data" "${BASE}/${name}/log"
  echo "  生成 ${conf}"
}

case "$NODE" in
  01)
    render_conf "rs1" 27101 "rs0" "" "0.0.0.0" "$SEC_AUTH"
    render_conf "cfg" 27201 "cfgRS" "configsvr" "0.0.0.0" "$SEC_AUTH"
    render_conf "mongos" 27400 "" "" "0.0.0.0" "sharding:
  configDB: cfgRS/192.168.121.128:27201
security:
  keyFile: ${KEYFILE}"
    ;;
  02)
    render_conf "rs2" 27102 "rs0" "" "0.0.0.0" "$SEC_AUTH"
    render_conf "shard1" 27301 "shard1" "shardsvr" "0.0.0.0" "$SEC_AUTH"
    ;;
  03)
    render_conf "rs3" 27103 "rs0" "" "0.0.0.0" "$SEC_AUTH"
    render_conf "shard2" 27302 "shard2" "shardsvr" "0.0.0.0" "$SEC_AUTH"
    # 单机：先用 127.0.0.1 无认证启动，建完三个账号后再换认证配置重启
    render_conf "standalone" 27017 "" "" "127.0.0.1" ""
    sed -e "s/^  bindIp: 127.0.0.1/  bindIp: 0.0.0.0/" \
        "${CONF_DIR}/standalone.conf" > "${CONF_DIR}/standalone-auth.conf"
    printf 'security:\n  authorization: enabled\n' >> "${CONF_DIR}/standalone-auth.conf"
    echo "  生成 ${CONF_DIR}/standalone-auth.conf"
    ;;
esac

echo "节点 ${NODE} (${IP}) 配置生成完成。"
