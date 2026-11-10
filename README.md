# 智慧图书馆数字资源平台（MongoDB 综合实践）

用文档数据库改造传统图书馆的关系型模型：把「图书 / 读者 / 借阅流水」三张表迁移到 MongoDB，
在同一套数据上完成**检索统计、二进制文件存取、三节点高可用与分片扩展**，并用一个 Python
命令行程序把全部能力串成可演示的菜单。配套三套部署形态：单机实例、三节点副本集 `rs0`、
「配置服务器 + 两个分片 + mongos」分片集群。

- **数据规模**：`books` 50 册、`readers` 30 位、`borrow_logs` 3000 条（2023-01 — 2025-12）、GridFS 6 个文件（3 本 PDF + 3 张封面，合计 180200 字节）
- **技术栈**：MongoDB 7.0（mongod / mongosh / mongos）、Python 3.12 + PyMongo 4.x、CentOS Stream 10
- **原始数据只读**：`data/raw/*.txt` 原样导入，日期字符串在内存中转成 BSON `Date` 后写库

## 主要功能

命令行主程序 `main.py` 提供 9 个一级功能：

| 菜单 | 能力 | 实现 |
| --- | --- | --- |
| 1 馆藏检索 | 6 类查询：分类+价格区间、标签多选（任一/全部）、书名模糊、出版年份区间、缺失标签、评分 Top10（投影三字段） | `book_manager.py` |
| 2 图书管理 | 按 ISBN 增删改查、分类枚举 | `book_manager.py` |
| 3 读者管理 | 姓名/学院检索、借阅史、新增与删除 | `reader_manager.py` |
| 4 借阅管理 | 借书（校验库存与在借数）、还书、逾期标记、流水查询、导出台账 | `borrow_manager.py` |
| 5 统计分析 | 分类统计、学院借阅 Top5、月度趋势、热门图书、读者等级/状态分布、活跃读者，并用 `$merge` 落库 `category_stats` | `stat_manager.py` |
| 6 电子书与封面 | GridFS 上传/列表/按书名下载，字节数与 MD5 双重校验 | `gridfs_manager.py` |
| 7 审计日志 | 写入固定集合 `audit_logs`，查询最近 100 条 | `audit_logger.py` |
| 8 数据库与集群状态 | 连接信息（口令打码）、`hello` 判定主从、集合文档计数 | `mongodb_connect.py` |
| 9 统计结果导出 | 统计结果导出为 JSON/CSV 到 `LIB_EXPORT_DIR` | `stat_manager.py` |

辅助脚本 `scripts/` 覆盖数据工程与运维取证：导入建索引建账号（`init_db.py`）、12 个索引的
建立/查看/删除（`create_indexes.py`）、数据量与字段类型核对（`verify_data.py`）、索引前后
耗时对比（`perf_index.py`）、检索与统计一次性演示（`task3_demo.py`）、GridFS 演示
（`gridfs_demo.py`）、5 种读偏好对比（`read_pref_demo.py`）。

## 数据模型

| 集合 | 说明 |
| --- | --- |
| `books` | 馆藏：ISBN 唯一，含 `category`、`tags[]`、`price`、`publish_date`(Date)、`rating`、`stock`、`borrow_count` |
| `readers` | 读者：借书证号唯一，含 `college`、`level`、`register_date`(Date)、在借数 |
| `borrow_logs` | 借阅流水 3000 条，`status` 区分在借/已还/逾期；**普通集合，不设 TTL** |
| `category_stats` | 统计结果物化表，由聚合 `$merge` 写入 |
| `audit_logs` | 固定集合（capped），记录关键写操作 |
| `fs.files` / `fs.chunks` | GridFS 存储电子书与封面 |

12 个索引覆盖上述检索路径，其中 `idx_shard_reader_borrowdate` 与分片键
`{reader_card: 1, borrow_date: 1}` 同向前缀，保证 `shardCollection` 能成功。

## 目录结构

```
.
├── main.py                  # 启动横幅 + 9 项主菜单
├── config.py                # 环境变量 → 连接参数（URI / 库名 / 读偏好 / 导出目录），口令打码
├── mongodb_connect.py       # 单例连接、hello 判定、集合计数
├── display.py               # 中文宽度对齐的表格输出
├── audit_logger.py          # 固定集合 audit_logs 写入与查询
├── book_manager.py          # 馆藏 6 类检索 + 增删改
├── reader_manager.py        # 读者检索、借阅史、增删
├── borrow_manager.py        # 借书 / 还书 / 逾期标记 / 流水查询 / 导出
├── stat_manager.py          # 5 组统计 + $merge 写 category_stats + 结果导出
├── gridfs_manager.py        # 上传 / 列表 / 按书名下载 + 字节与 MD5 校验
├── requirements.txt         # pymongo 等依赖
├── .env.example             # 环境变量样例（不含任何真实口令）
├── scripts/                 # 数据工程与验证脚本
│   ├── init_db.py           # 只读导入 → 日期转换 → 建索引 → 建账号 → GridFS
│   ├── create_indexes.py    # 12 个索引的建立 / 查看 / 删除
│   ├── verify_data.py       # 数量、字段类型、数据质量、索引清单核对
│   ├── perf_index.py        # 4 条查询的索引前后耗时对比（批量计时取中位数）
│   ├── task3_demo.py        # 11 项检索 + 5 组统计的一次性演示
│   ├── gridfs_demo.py       # 上传 6 个文件、列出元数据、按书名下载校验
│   ├── read_pref_demo.py    # 5 种读偏好 + 从节点直读对比
│   ├── export_archive.py    # 全库归档导出
│   └── reimport_*.py        # 单集合重导入（books / borrow_logs）
├── deploy/                  # 三节点部署脚本
│   ├── bootstrap.sh         # 建目录、生成配置、生成/分发 keyFile
│   ├── render_confs.sh      # 按节点渲染 mongod / mongos 配置
│   ├── manage.sh            # 启停 / 状态
│   ├── 03_standalone/       # 单机实例 + 开启认证 + 三套账号权限验证
│   ├── 02_replicaset/       # init_rs.js、check_rs.js、failover_probe.py、节点增删
│   └── 03_sharding/         # init_cfg.js、init_shard.js、shard_collection.js、分片分布校验
├── data/raw/                # 课程原始数据（只读）
│   ├── books.txt / readers.txt / borrow_logs.txt
│   └── gridfs_files/        # GridFS 待上传清单
└── docs/                    # 报告正文源文件、答辩讲稿、运行证据
    ├── report.md            # 项目报告正文（Markdown 源）
    ├── 答辩讲稿.md
    └── evidence/            # 数据画像、数量核对、性能对比、副本集状态等原始输出
```

## 部署拓扑（3 台虚拟机，非特权端口）

| 实例 | 节点 | 端口 | 数据目录（`~/final` 下） |
| --- | --- | --- | --- |
| 单机 standalone | nosql03 | 27017 | `standalone/data` |
| 副本集 rs0 | nosql01 / 02 / 03 | 27101 / 27102 / 27103 | `rs1/data`、`rs2/data`、`rs3/data` |
| 配置服务器 cfgRS | nosql01 | 27201 | `cfg/data` |
| 分片 shard1 | nosql02 | 27301 | `shard1/data` |
| 分片 shard2 | nosql03 | 27302 | `shard2/data` |
| 路由 mongos | nosql01 | 27400 | 无 dbPath（只存日志） |

实验环境的三台机器为 `192.168.121.128/129/130`，脚本中的地址可按自己的环境修改。

## 快速开始

```bash
pip install -r requirements.txt

# 1) 起实例（以单机为例；副本集 / 分片见 deploy/ 下对应目录）
bash deploy/bootstrap.sh 03
bash deploy/manage.sh 03 start standalone

# 2) 导入数据、建索引、建账号、传 GridFS（账号口令走环境变量）
export LIB_PWD_READONLY='<只读账号口令>'
export LIB_PWD_READWRITE='<读写账号口令>'
export LIB_PWD_ADMIN='<管理账号口令>'
export LIB_PWD_CLUSTER='<集群管理口令>'
python3 scripts/init_db.py --data-dir data/raw --with-users

# 3) 连接信息只用环境变量注入，代码里没有硬编码连接串
export LIB_DB_URI='mongodb://lib_writer:<password>@127.0.0.1:27017/library?authSource=library'
python3 main.py                # 9 项菜单
python3 scripts/verify_data.py # 数量与类型核对
python3 scripts/perf_index.py  # 索引前后耗时对比
```

副本集场景另加 `LIB_DB_REPLICA_SET=rs0`，读偏好用 `LIB_DB_READ_PREF` 指定；
分片集群直接连 mongos 的 `LIB_DB_URI` 即可。

## 账号与权限

四个账号按最小权限划分，**口令不入库、不入代码**，建号脚本从环境变量读取：

| 账号 | 角色 | 用途 |
| --- | --- | --- |
| `lib_reader` | `read` | 只读：检索与报表，写入会被拒绝 |
| `lib_writer` | `readWrite` | 业务程序日常增删改 |
| `lib_admin` | `dbAdmin` + `userAdmin` + `readWrite` | 建索引、建账号、维护 |
| `cluster_admin` | `root`（admin 库） | 副本集 / 分片运维 |

## 文档

- `docs/report.md`：报告正文（选型论证、建模、检索统计、索引优化、副本集、分片、风险清单）
- `docs/答辩讲稿.md`：8 分钟答辩口径
- `docs/evidence/`：数据画像、数量核对、性能对比、任务三演示、GridFS、读偏好、副本集状态等原始输出

## 说明

- 公开版本已做匿名化处理：报告与讲稿中的成员姓名、学号以「成员 A/B/C」替代，运行证据里的
  家目录用户名统一写作 `~/final`；如需署名版本请向作者索取。
- 本仓库只收录源码、部署脚本、原始数据与文字材料；报告 Word/PDF、答辩 PPT、验收截图等
  二进制交付物体积较大（约 70 MB），未纳入版本库。
- 仓库中不包含任何明文口令；`scripts/init_db.py` 与 `deploy/` 下的建号脚本一律从环境变量
  `LIB_PWD_*` 读取口令。
- `borrow_logs` 不设 TTL：按 5 年保留期设计，设 2 年会误删历史流水。
- 分片操作顺序必须是**先 `shardCollection` 建分片键、再导入数据**，反过来会产生孤儿文档。
