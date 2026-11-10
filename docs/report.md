---
title: "智慧图书馆数字资源平台——MongoDB 综合实践报告"
---

# 1 项目概述与分工

## 1.1 项目背景

本次实践要求把传统图书馆的三张关系表（图书、读者、借阅流水）改造成文档数据库实现，并在此基础上完成检索统计、二进制文件存储、三节点高可用与分片扩展。数据来自课程配套的三份原始文件：馆藏 `books` 50 册、读者 `readers` 30 位、借阅流水 `borrow_logs` 3000 条（2023-01 至 2025-12），另有三本 PDF 电子书与三张封面需存入 GridFS。原始数据按"不改一行"的原则只读导入，日期字符串在内存中转换为 BSON Date 后再写库。

## 1.2 部署环境

| 项目 | 配置 |
| --- | --- |
| 虚拟机 | VMware Workstation，3 台 CentOS Stream 10，各 2 vCPU / 4 GB 内存 |
| 节点 | nosql01 192.168.121.128、nosql02 192.168.121.129、nosql03 192.168.121.130 |
| 数据库 | MongoDB 7.0.45（mongod / mongosh / mongos 同版本），副本集 rs0 + 分片集群 |
| 程序 | Python 3.12.14、pymongo 4.19.0，命令行菜单程序（9 个一级功能） |
| 认证 | keyFile 内部认证 + 三套 library 业务账号（只读/读写/管理） |

三个实例角色互不冲突：nosql03:27017 是任务三的单机实例；nosql01/02/03 的 27101–27103 组成副本集 rs0；27201 是分片配置服务器，27301/27302 是两个分片，27400 是 mongos。所有实例都用普通用户 `<user>` 的家目录，不依赖 root，端口全部为非特权端口。

## 1.3 三人分工

| 成员 | 负责模块 | 具体工作 |
| --- | --- | --- |
| 成员 A | 数据与程序 | 数据画像与清洗、集合/字段建模、导入与数量核对、11 项检索与 5 组统计、12 个索引与执行计划对比、Python 菜单程序 9 个模块、GridFS 上传下载校验、三套业务账号权限验证 |
| 成员 B | 架构与运维 | 三节点端口与目录规划、单机实例部署、副本集初始化与 keyFile 认证、读偏好与故障转移演练、节点增删、配置服务器/两分片/mongos 搭建、分片键预分片与均衡、分片集群访问控制、部署脚本与证据采集脚本 |
| 成员 C | 文档与验收 | 选型论证（四类 NoSQL 对比、CAP/BASE 落地、风险清单）、报告统稿与排版、Compass 数据量与聚合核对、35 张验收截图整理、8 分钟答辩 PPT 与讲稿、提交包打包与自查 |

## 1.4 进度安排

| 阶段 | 时间 | 交付 |
| --- | --- | --- |
| 选型与建模 | 第 1—3 天 | 选型论证 1 份、字段类型表、索引清单 |
| 单机与数据 | 第 4—6 天 | 自定义 dbpath 实例、50/30/3000 导入核对、11 项检索 |
| 程序与文件 | 第 7—9 天 | 9 模块菜单程序、GridFS 6 个文件、审计日志 |
| 副本集 | 第 10—11 天 | 1 主 2 从、读偏好对比、故障转移过程记录 |
| 分片 | 第 12—13 天 | cfg + 2 分片 + mongos、3000 条流水分布验证 |
| 验收与文档 | 第 14 天 | Word/PDF、35 张截图、答辩 PPT |

# 2 选型论证

## 2.1 四类 NoSQL 对比

| 维度 | 键值（Redis） | 文档（MongoDB） | 列族（HBase/Cassandra） | 图（Neo4j） |
| --- | --- | --- | --- | --- |
| 数据模型 | key → value，无结构 | BSON 文档，字段可嵌套可缺失 | 行键 + 列族 + 时间戳 | 节点 + 关系 + 属性 |
| 查询能力 | 仅按 key 命中 | 等值/范围/数组/正则/聚合管道/地理 | 按行键前缀扫描，二级索引需 Phoenix | 多跳关系遍历强，聚合弱 |
| 一致性 | 单机强，集群最终一致 | 副本集可调（w:majority 强、读偏好最终） | 可调一致性，写吞吐高 | 主从强一致 |
| 扩展方式 | 分片/集群 | 原生分片（range/hashed/zone） | 水平分片，按行键预分区 | 因果集群，写扩展有限 |
| 典型场景 | 会话、缓存、计数 | 内容管理、目录、日志、半结构化 | 海量时序/宽表、写入密集 | 社交关系、知识图谱 |
| 本项目适配 | 只能做库存计数，检索统计弱 | 馆藏/读者/流水三类实体天然文档，聚合满足 11 项检索 | 流水可放，但馆藏检索与嵌套字段查询不便 | 借阅网络可建模，但 50 册馆藏不值得 |

选择文档数据库的核心原因是：三类实体字段差异大（图书有嵌套 `location`、读者有可空 `email`、流水有可缺 `return_date`），文档模型允许同集合内字段缺失而不必用 NULL 占位；11 项检索里既有数组多选（`tags`）、又有日期区间、还有 `$lookup` 关联统计，MongoDB 的查询与聚合管道能一条语句完成，不需要额外计算引擎。

## 2.2 CAP 在两个业务场景下的取舍

**场景一：馆藏查询（读多写少）**。读者检索书名、按分类价格筛选，容忍几百毫秒到几秒的陈旧数据。这类请求落到 CAP 的 AP 侧：副本集允许从节点提供读，读偏好用 `secondaryPreferred`，主节点故障期间查询仍可从从节点返回，牺牲的是"刚上架的图书可能查不到"这种极短时间的不一致。

**场景二：借阅流水写入（写必须落地）**。办理借书要同时写 `borrow_logs` 并扣减 `books.stock`，写失败意味着读者和馆员看到的状态不一致。这里取 CP 侧：写关注 `w:majority` + `j:true`，保证多数派落盘后才应答；主节点故障时写会短暂失败（实测 4.4—4.9 秒选出新主），程序把失败翻译成"系统繁忙，请重试"，而不是静默丢单。

## 2.3 BASE 哪些能接受、哪些不能

可以接受最终一致的是**统计类**：分类统计集合 `category_stats` 通过 `$merge` 定时重建，榜单、年月趋势允许落后于流水几秒——它们只用于展示，不参与业务判断。

不能接受最终一致的是**库存扣减**。若库存用"读—改—写"两步完成，两次借阅并发时会出现超借。实现上把扣减收敛成单文档原子操作：`updateOne({isbn, stock: {$gt: 0}}, {$inc: {stock: -1, borrow_count: 1}})`，返回 `matchedCount=0` 即库存不足；同一读者重复借同一本书由"未还记录唯一性检查"拦截。单文档更新在 MongoDB 中天然原子，不需要跨文档事务。

## 2.4 两个潜在风险与应对

**风险一：内嵌数组无界增长**。如果把借阅流水嵌进 `books` 或 `readers` 文档，3000 条流水会让单个文档无限膨胀（16 MB 上限、每次读写整文档）。应对：`tags`、`fav_categories`、`location` 这类有界且随主体一起读的字段才内嵌；`borrow_logs` 独立成集合，用 `reader_card`、`book_isbn` 引用，统计时 `$lookup` 关联。

**风险二：多集合写入缺少跨文档事务的一致性**。借书要写流水 + 扣库存，若第一步成功第二步失败就出现"有流水无扣减"。应对：把扣库存放在前面（失败则直接返回，不留脏流水），流水写入失败时用补偿更新把库存加回；对一致性要求更高的场景可启用 4.0+ 多文档事务（本项目实验环境为单节点分片，事务可用但不作为主路径）。

## 2.5 给非技术决策者的说明（198 字）

我们选 MongoDB，是因为图书馆的数据像"卡片"：每本书的字段不完全一样，有的有标签、有的没有电子书；读者有的留邮箱、有的没留。传统表格要求每行字段整齐，缺了就得填空值；文档数据库允许"缺就是不写"，改起来也不用改表结构。检索时，按分类、价格、标签、出版年份组合筛选，一条语句就能出结果；借阅流水单独存一张"流水账"，三年 3000 条也不会拖慢图书查询。三台机器组成副本集，一台坏了另一台几秒内接班；数据再涨，加机器分片即可，不需要停机迁移。

# 3 数据建模

## 3.1 层次结构

```
library（数据库）
├── books（集合，50 文档）：isbn, title, author, publisher, category,
│     price, rating, stock, tags[], publish_date, borrow_count, ebook_name,
│     location{floor, shelf, copies}
├── readers（集合，30 文档）：card_no, name, college, email, phone,
│     level, register_date, fav_categories[]
├── borrow_logs（集合，3000 文档）：borrow_date, return_date, reader_card,
│     book_isbn, status, duration_days
├── audit_logs（固定集合，16 MB / 50000 条）：ts, actor, role, action,
│     collection, target, detail, result, source
├── category_stats（集合，6 文档）：_id=分类, book_count, avg_price,
│     avg_rating, total_stock, borrow_total
└── fs.files / fs.chunks（GridFS）：电子书 PDF 与封面 PNG
```

## 3.2 字段与 BSON 类型

| 集合 | 字段 | BSON 类型 | 说明 |
| --- | --- | --- | --- |
| books | isbn | String | 业务主键，建唯一索引 |
| books | title / author / publisher / category | String | category 限定 6 类 |
| books | price | Double | 元，保留 1 位小数 |
| books | rating | Double | 0—5 分 |
| books | stock / borrow_count | Int32 | 可借册数 / 累计借阅次数 |
| books | tags | Array&lt;String&gt; | 部分文档缺失该字段 |
| books | publish_date | Date | 原始为 ISO8601 字符串，导入时转 Date |
| books | ebook_name | String 或 null | 仅 3 本有电子书 |
| books | location | Object | 内嵌 floor/shelf/copies |
| readers | card_no | String | 唯一索引 |
| readers | email | String 或 null | 5 位读者为 null |
| readers | level | String | 普通/高级/教师 |
| readers | register_date | Date | 导入时转 Date |
| readers | fav_categories | Array&lt;String&gt; | 2 位读者缺失 |
| borrow_logs | borrow_date / return_date | Date | return_date 未归还时字段缺失 |
| borrow_logs | reader_card / book_isbn | String | 引用 readers / books |
| borrow_logs | status | String | 已归还/借出/逾期 |
| borrow_logs | duration_days | Int32 | 借阅天数，未归还时为 0 |
| audit_logs | ts | Date | 操作时间，建降序索引 |
| audit_logs | actor / role / action / collection / target / detail / result / source | String | 谁、以什么角色、做了什么、对哪个集合的哪个对象、结果如何、来自哪里 |

## 3.3 三个最容易写错的字段

**price 用 Double 而不是字符串或 Decimal128**。原始数据里价格形如 `89.0`，若按字符串存，`$gte: 50` 会变成字典序比较（"100" < "50"）；若用 Decimal128，Python 侧要显式 `Decimal128` 包装、聚合里 `$avg` 还要再转，代价大于收益。图书馆场景不需要金融级精度，Double 的 15 位有效数字足够，聚合统计时用 `$round` 控制小数位。

**publish_date / register_date / borrow_date 必须是 Date**。原始文件里是 `"2023-03-01T00:00:00.000+08:00"` 这样的字符串，直接入库后 `$gte: ISODate("2018-01-01")` 全部匹配失败，`$dateToString` 也无法按年月分组。导入脚本在内存中统一 `datetime.fromisoformat` 转换，并用 `verify_data.py` 抽查 `isinstance(value, datetime)`，避免"看起来能查、其实全表扫描"的假通过。

**status 与 return_date 的语义要成对设计**。已归还有 `return_date`，借出与逾期没有；若查询"未归还"写成 `{return_date: null}`，会把"字段不存在"和"显式 null"混在一起（本数据里两者恰好等价，但换成别的数据源就不成立）。程序里统一用 `{"return_date": {"$exists": False}}` 或 `status: {$in: ["借出","逾期"]}` 表达同一业务含义，并在建模文档里写清"缺失即未归还"的约定。

## 3.4 location 为什么内嵌、什么时候该拆

`location` 是"这本书放在哪"的三个紧邻属性，随图书一起被读取（检索结果要显示楼层书架），拆成独立集合同一次查询就多一次 `$lookup`，而它本身有界（每本书只有一个位置），因此内嵌。**该拆的信号**有三个：一是书架信息需要独立维护（同一书架换楼层，要让该架上所有书跟着变，内嵌就得批量更新）；二是位置要单独统计（按楼层统计藏书量、按书架查空位）；三是同一位置被大量文档重复描述（`floor` 文案改了要改 50 份）。出现任一情况就建 `shelves{floor, shelf, capacity}` 集合，`books` 里只留 `shelf_id`。

## 3.5 borrow_logs 的集合类型与关键参数

`borrow_logs` 选择**普通集合**，理由是业务需要"改"：还书时要补 `return_date`、把 `status` 从"借出"改成"已归还"、写回 `duration_days`。时间序列集合的更新限制很硬——只能按 `metaField` 匹配、只能修改 `metaField`、必须用 `updateMany`、禁止 upsert，任务四的"还书"写不进去。此外 3000 条流水分布在三年里，平均每天 2.7 条，每条都是"某读者借了某本书"的一次性事件，`{reader_card, book_isbn}` 组合几乎条条唯一，按时间分桶后每个桶只有一两条，压缩收益接近零。时间序列还不支持唯一索引、text 索引与事务写入，集合类型创建后不能转换，选错就要新建集合并迁移 3000 条。**评估过的备选**是 `timeseries{timeField: borrow_date, metaField: {reader_card, book_isbn}, granularity: hours}`，它能省空间、按时间范围扫描快，但与"更新状态"的业务模型冲突，故弃用；如果业务改成不可变事件流（借出、归还各追加一条，状态由最新事件推导），时间序列才是合适选择。

关键参数：不设 `expireAfterSeconds`（历史流水要留 5 年以上，按秒计为 157680000，绝不能用 2 年的 63072000，否则 2023—2024 的数据会被 TTL 线程清空）；写关注 `w:majority`；分片键 `{reader_card: 1, borrow_date: 1}`（见 6.3）。

## 3.6 audit_logs 的设计

审计日志用**固定集合**（capped，16 MB / 50000 条），写入是追加式的，天然按插入顺序排列，超过容量自动覆盖最旧文档，不需要清理任务。字段：`ts`（Date）、`actor`（账号）、`role`（read/readWrite/admin）、`action`（新增/修改/删除/导出/上传/下载等）、`collection`、`target`（ISBN 或卡号）、`detail`（变更内容摘要）、`result`（成功/失败）、`source`（program/script）。"按时间倒序取最近 100 条"用 `find().sort([("$natural", -1)]).limit(100)`，固定集合的 `$natural` 就是插入顺序，比按 `ts` 排序更稳（同一毫秒内的多条也不会乱序）；同时建 `ts` 降序与 `(action, ts)` 索引支持按动作过滤。写入审计失败只记警告不抛异常，避免审计库故障阻断业务。

## 3.7 索引清单

| 集合 | 索引 | 键 | 用途 |
| --- | --- | --- | --- |
| books | uk_isbn | {isbn: 1} unique | 业务主键、防重复导入 |
| books | idx_category_price | {category: 1, price: 1} | 分类 + 价格区间检索（Q1） |
| books | idx_tags | {tags: 1} | 标签多选 `$in` / `$all` |
| books | idx_publish_date | {publish_date: -1} | 出版年份区间、新书排序 |
| books | idx_rating_borrow | {rating: -1, borrow_count: -1} | 评分 Top10 稳定排序 |
| readers | uk_card_no | {card_no: 1} unique | 借书证唯一 |
| readers | idx_college_level | {college: 1, level: 1} | 学院借阅统计、等级筛选 |
| readers | idx_name | {name: 1} | 姓名模糊查询前缀 |
| borrow_logs | idx_reader_borrowdate | {reader_card: 1, borrow_date: -1} | 读者借阅流水（Q2） |
| borrow_logs | idx_book_borrowdate | {book_isbn: 1, borrow_date: -1} | 某书的借阅历史 |
| borrow_logs | idx_status_borrowdate | {status: 1, borrow_date: -1} | 按状态过滤（Q3） |
| borrow_logs | idx_borrowdate | {borrow_date: -1} | 年月趋势、日期区间（Q4） |
| borrow_logs | idx_shard_reader_borrowdate | {reader_card: 1, borrow_date: 1} | 分片键前缀（方向必须与分片键一致） |

# 4 功能实现

## 4.1 单机实例与数据导入

单机实例在 nosql03 上，自定义数据目录 `~/final/final/standalone/data`，端口 27017，先以 `127.0.0.1` 无认证启动完成导入，再切换到 `0.0.0.0` + `authorization: enabled` + keyFile 的配置文件。导入脚本 `scripts/init_db.py` 只读原始文件，逐条把 ISO8601 字符串转 `datetime`，写入后立即核对数量。

| 集合 | 期望 | 实际 | 结论 |
| --- | --- | --- | --- |
| books | 50 | 50 | 通过 |
| readers | 30 | 30 | 通过 |
| borrow_logs | 3000 | 3000 | 通过 |
| fs.files / fs.chunks | 6 / 6 | 6 / 6 | 通过（总 180200 字节） |

## 4.2 十一项检索与统计

| 编号 | 需求 | 实现要点 | 结果 |
| --- | --- | --- | --- |
| 检索 1 | 分类 + 价格区间 | `{category, price: {$gte, $lte}}`，走复合索引 | 计算机类 50—120 元共 8 册 |
| 检索 2 | 标签多选 | `$in`（任一）/ `$all`（全部） | Python 或编程命中 4 册，Python 且编程命中 2 册 |
| 检索 3 | 书名模糊 | 关键字转义后 `$regex` + `$options: "i"` | 含"数据"共 3 册 |
| 检索 4 | 出版年份区间 | 拼接 `Date` 边界后 `$gte/$lte` | 2018—2020 年共 8 册 |
| 检索 5 | 缺失 tags | `$or: [{tags: {$exists: false}}, {tags: null}, {tags: []}]` | 4 册（百年孤独、飘、哥德尔证明、局外人） |
| 检索 6 | 评分 Top10 | `sort({rating:-1, borrow_count:-1})` + projection 三字段 | 首位《活着》4.9 |
| 统计 1 | 分类统计 | `$group` + `$avg` + `$round` | 6 个分类，计算机 15 册、均价 89.53、借阅 2049 次 |
| 统计 2 | 学院借阅 Top5 | 流水 `$lookup` readers，`$addToSet` 后 `$size` | 计算机学院 500、经济管理学院 500、数学与统计学院 400 |
| 统计 3 | 年月趋势 | `$dateToString: {format: "%Y-%m"}` | 37 个月，2023-03 峰值 87 次 |
| 统计 4 | 借阅最多 10 本 | `$lookup` books 取 `location` | 前 10 名并列 60 次，带楼层书架 |
| 统计 5 | 统计写入新集合 | `$merge` 到 `category_stats` | 6 个分类文档，可重复执行 |

## 4.3 索引优化前后对比

`scripts/perf_index.py` 对同一条查询先在"删掉相关索引"的状态下采样，再建索引采样，每批 50 次、5 批取中位数，避免毫秒级计时抖动。四条查询的对比：

| 查询 | 命中 | 扫描文档（前→后） | 单次中位数（前→后） | 提速 |
| --- | --- | --- | --- | --- |
| Q1 分类 + 价格区间 | 8 | 50 → 8 | 1.597 → 1.281 ms | 1.25× |
| Q2 读者流水倒序取 20 | 20 | 594 → 20 | 3.866 → 1.329 ms | 2.91× |
| Q3 状态过滤取 20 | 20 | 28 → 20 | 1.658 → 2.014 ms | 0.82×（变慢） |
| Q4 借阅日期区间 | 50 | 3000 → 50 | 5.365 → 1.726 ms | 3.11× |

Q1 的执行计划从 `SORT` 变成 `LIMIT`，说明复合索引同时承担了过滤与排序；Q2、Q4 的扫描文档数分别降到 1/29.7 与 1/60。**Q3 反而变慢**，原因是 `status` 只有三个取值且"已归还"占 2142/3000，索引选择性极低，优化器仍要回表取 20 条完整文档，额外索引跳转反而增加开销——这条结果没有删掉，而是作为"索引不是越多越好"的证据保留在报告里，并在第 7 章讨论。

## 4.4 三账号访问控制

| 操作 | lib_reader（read） | lib_writer（readWrite） | lib_admin（dbAdmin+userAdmin+readWrite） |
| --- | --- | --- | --- |
| 查询馆藏/流水 | 允许 | 允许 | 允许 |
| 插入、更新、删除文档 | 拒绝（Unauthorized / 13） | 允许 | 允许 |
| 创建/删除索引 | 拒绝 | 允许（readWrite 内置含建索引） | 允许 |
| 创建账号 | 拒绝 | 拒绝 | 允许 |
| 删除数据库 | 拒绝 | 拒绝 | 允许 |

"读写账号能不能建索引"是常见误区：MongoDB 的 `readWrite` 内置角色本身就包含 `createIndex`、`dropIndex`，真正属于管理员的操作是建账号、删库、改副本集配置。验证脚本 `verify_writer.js` 把这条边界写进了断言，避免答辩时被问住。

## 4.5 Python 菜单程序

程序按功能拆成 9 个模块，连接参数全部走环境变量，不在代码里硬编码主机、端口与密码：

| 文件 | 职责 |
| --- | --- |
| config.py | 读取 `LIB_DB_*` 环境变量，拼 URI，`quote_plus` 转义密码，输出打码连接串 |
| mongodb_connect.py | 单例连接、`hello` 判定 mongos/副本集、集合计数、读偏好参数 |
| display.py | 中英文宽度对齐的表格、标题、键值块、日期格式化 |
| audit_logger.py | 审计写入与最近 100 条查询、按动作汇总 |
| book_manager.py | 6 类馆藏检索、增删改、分类列举 |
| reader_manager.py | 读者检索、借阅史、增删 |
| borrow_manager.py | 借书（校验读者/库存/重复未还）、还书、逾期标记、流水查询与导出 |
| stat_manager.py | 5 组统计、`$merge` 写入 category_stats、统计结果导出 |
| gridfs_manager.py | 上传（写 ISBN/类型/原名元数据）、列表、按书名下载并校验字节与 MD5 |
| main.py | 启动横幅 + 9 项一级菜单 + 异常兜底 |

一级菜单为：1 馆藏检索、2 图书管理、3 读者管理、4 借阅管理、5 统计分析、6 电子书与封面、7 审计日志、8 数据库与集群状态、9 统计结果导出。新增、删除、导出、上传、下载都会写 `audit_logs`，程序退出后可在菜单 7 看到最近 100 条操作记录。

## 4.6 图形化核对（MongoDB Compass）

命令行能证明数字，但老师与同事更信任"看见"的结果，所以用 Compass 1.53.0 再核一遍。连接 `192.168.121.130:27017/library` 后，数据库页直接给出每个集合的文档数、索引数与数据大小：`books` 50 个文档 / 6 个索引、`readers` 30 / 4、`borrow_logs` 3K / 5、`audit_logs` 22 / 3（带 `CAPPED` 标记，印证固定集合）、`fs.files` 与 `fs.chunks` 各 6、`category_stats` 6。

聚合结果同样在 Compass 里交叉验证：在 `borrow_logs` 的 Documents 页填入筛选条件 `{status: "已归还"}`，结果条数显示为 `1–25 of 2142`，与命令行 `$group` 统计出的"已归还 2142 / 借出 429 / 逾期 429"完全吻合；`readers` 的 30 与 `books` 的 50 也分别对应导入时的核对值。图形化核对的价值不在替代脚本，而在于换一条独立路径验证同一结论——如果两边对不上，问题一定出在脚本的连接串、库名或读偏好上。

除聚合之外，Compass 的 Indexes 页还逐表列出了索引名与键模式，与 `create_indexes.py` 的 12 条清单、以及 `borrow_logs` 上补建的 `idx_shard_reader_borrowdate` 一一对应，可直接用于验收对照。

# 5 文件存储（GridFS）

GridFS 把一个大文件切成 255 KB 的 `chunks` 文档，另在 `fs.files` 里存一条元数据文档，读取时按 `files_id` + `n` 顺序拼回。本项目上传 3 本 PDF 电子书与 3 张封面，元数据包含 ISBN、类型（ebook/cover）、原始文件名、内容类型、上传时间、字节数与 MD5，`books.ebook_name` 通过文件名与 `fs.files.filename` 关联。

| 文件 | ISBN | 类型 | 字节数 | 校验 |
| --- | --- | --- | --- | --- |
| ebook_1.pdf | 9787115428028 | ebook | 39837 | 字节一致、MD5 一致 |
| ebook_2.pdf | 9787121362726 | ebook | 38524 | 字节一致、MD5 一致 |
| ebook_3.pdf | 9787115546081 | ebook | 37004 | 字节一致、MD5 一致 |
| cover_1.png | 9787115428028 | cover | 23611 | 上传成功 |
| cover_2.png | 9787121362726 | cover | 26053 | 上传成功 |
| cover_3.png | 9787115546081 | cover | 15171 | 上传成功 |

按书名下载的链路是：先用书名关键字在 `books` 上做正则匹配拿到 `isbn`，再用 `metadata.isbn` 在 `fs.files` 里找文件，下载后比对"期望字节数 = `fs.files.length`"与 MD5，两项都一致才算成功。三本书的实测结果都是 `39837/39837 字节、MD5一致=True` 这样的输出，说明下载链路没有截断或编码损坏。

# 6 架构演进：副本集与分片

## 6.1 副本集拓扑与初始化

| 节点 | 端口 | 角色 | 优先级 |
| --- | --- | --- | --- |
| nosql01 | 27101 | PRIMARY | 2 |
| nosql02 | 27102 | SECONDARY | 1 |
| nosql03 | 27103 | SECONDARY | 1 |

`rs.initiate()` 后约 11 秒选出主节点，`rs.status()` 显示 1 主 2 从、复制延迟 0。节点间用同一份 keyFile（1024 字节，权限 400）做内部认证，业务账号建在 `library` 库，`cluster_admin` 建在 `admin` 库；首个账号通过 localhost exception 创建，之后立即关闭异常通道。

## 6.2 读偏好与故障转移

| 读偏好 | 实测平均 | 适用场景 |
| --- | --- | --- |
| primary | 14.7 ms | 刚还书后立即回显库存，必须读到最新 |
| primaryPreferred | 8.9 ms | 默认读法，主挂了自动降级读从 |
| secondaryPreferred | 13.5 ms | 榜单、报表，分摊主节点压力 |

三种偏好在主节点健康时都能读到数据；直连 192.168.121.129:27102 读到《百年孤独》、直连 192.168.121.130:27103 读到《深入理解计算机系统（第3版）》，证明从节点确实在提供服务。**故障转移记录**：停掉主节点进程后约 0.5 秒，旧主进入 quiesce 模式（`NotPrimaryError: The server is in quiesce mode and will shut down`）；约 4.4 秒后 nosql02 被选为新主（多轮复测 4.4—4.9 秒）；期间副本集客户端以 100 ms 间隔连续发起的 55—63 次读、55—63 次写**全部成功**，这是 pymongo 的拓扑刷新与可重试写把请求透明切到了新主；旧进程完全退出用了 16.1—16.6 秒（mongod 关机前的 quiesce 窗口），重启后 2.0—3.1 秒以 SECONDARY 身份重新加入，最终回到 1 主 2 从。直接连旧主地址的客户端则会看到 `ServerSelectionTimeoutError`，这就是"应用要连副本集地址、不要连单节点地址"的实证。

## 6.3 节点增删演练

`rs.remove("192.168.121.130:27103")` 后成员数从 3 变 2，剩余节点继续选主与读写；`rs.add("192.168.121.130:27103")` 后恢复 3 成员，nosql03 以 SECONDARY 身份重新同步，直读核对 50/30/3000 与主库一致。增删过程中无需停机，说明副本集可以按需扩容缩容。

## 6.4 分片集群拓扑

| 组件 | 位置 | 说明 |
| --- | --- | --- |
| 配置服务器 cfgRS | nosql01:27201 | 单节点副本集，`clusterRole: configsvr` |
| 分片 shard1 | nosql02:27301 | 单节点副本集（shardsvr 必须配 replSetName） |
| 分片 shard2 | nosql03:27302 | 单节点副本集 |
| 路由 mongos | nosql01:27400 | 连接 cfgRS，配置 keyFile 与认证 |

两个分片都做成"单节点副本集"而不是独立进程，因为 `clusterRole: shardsvr` 的 mongod 不允许以 standalone 启动（会直接退出并提示 `Cannot start a shardsvr as a standalone server`），而单节点副本集既满足要求，又保留了 oplog 与后续扩容成三节点的空间。`sh.addShard` 必须用副本集 URL 形式 `shard1/192.168.121.129:27301`，直接写 `host:port` 会报 `host is part of set shard1; use replica set url format`。

## 6.5 分片键论证（选择 {reader_card: 1, borrow_date: 1}）

**基数**。`reader_card` 有 30 个不同值，组合 `borrow_date` 后几乎每条流水都不同，3000 条数据可以切成任意多块，不会出现"一个值占满一个分片"的倾斜；相比之下 `status` 只有 3 个值，作为分片键最多切三块，属于典型的低基数反例。

**写分布**。每个读者的流水量在 60—140 条之间，30 位读者在三年里均匀借书，按 `reader_card` 范围切分后两个分片各拿 1500 条，写入压力接近 1:1；若按 `book_isbn` 分片，热门书（借阅 60 次以上）会把写集中到少数 chunk 上。

**查询支持**。业务里最高频的"某读者最近借了什么"带 `reader_card` 等值条件，分片键前缀命中后 mongos 只向一个分片下发查询（定向查询）；`borrow_date` 作为第二列支持"某读者某时间段"的范围扫描。反过来，"全部逾期记录"这类不带读者条件的查询必然广播到所有分片，这是范围分片键的固有代价，靠预分片把块数控制在 2 个、每片 1500 条来限制代价。

**备选方案对比**。备选一是 `{book_isbn: 1}`：基数 50，写会向热门书倾斜，且"读者借阅史"查询要广播；备选二是 `{reader_card: "hashed"}`：写分布最均匀，但哈希后范围查询退化为全分片扫描，"某读者最近一个月"也要广播，且无法利用 `borrow_date` 做块内有序；备选三是 `{status: 1, borrow_date: 1}`：低基数导致块无法再切，且状态会变化（借出→已归还），更新分片键会触发文档迁移，运维代价高。综合基数、写均匀、查询覆盖与运维成本，选 `{reader_card: 1, borrow_date: 1}`。

## 6.6 分布验证与查询对比

建分片键前先预分片：`splitAt({reader_card: "R20240016", borrow_date: ISODate("1970-01-01")})` 把键空间切成两段，再把上界块 `moveChunk` 到 shard2，避免 3000 条全落在主分片。`getShardDistribution()` 显示两片各 1500 条、各 1 个 chunk，数据量 49.97% 与 50.02%。这里有一个必须说明的现象：`shardCollection` 之前导入的数据会先落在主分片，分片后主分片上的旧文档成为"孤儿"，`config.rangeDeletions` 里出现 `numOrphanDocs: 1500`，由后台线程在 900 秒后清理；因此 `getShardDistribution()` 短暂显示 shard2 有 3000 条（1500 有效 + 1500 孤儿），实际有效分布仍是 1:1。**正确顺序是"先建分片键、再导入"**，脚本 `reshard_after_import.sh` 已按这个顺序固化。

| 查询 | 涉及分片 | 返回 | 扫描文档 | 单次耗时 | 20 次平均（首轮） |
| --- | --- | --- | --- | --- | --- |
| 定向：某读者 + 日期区间 | shard1 | 100 | 100 | 5—7 ms | 10.35 ms |
| 跨分片：状态=已归还 | shard1, shard2 | 2142 | 3213 | 17—20 ms | 72.80 ms |

定向查询只落到一个分片、扫描 100 条文档；跨分片查询要合并两片结果，平均耗时约为定向的 7 倍。注意表中是首轮测量值，复测一轮得到 18.00 ms 与 123.95 ms（截图 t6_03 即复测记录），绝对值随机器负载波动，但"跨分片约为定向的 6—7 倍"这个结论稳定。这个 7 倍差距说明"分片键要覆盖高频查询条件"不是理论口号，而是可以直接测出来的成本。

## 6.7 集群访问控制与生产化建议

分片集群同样启用 keyFile 与三套账号：在 mongos 上用 `lib_reader` 连接时，`insert`/`update`/`deleteMany` 全部返回 `Unauthorized / 13`，`lib_writer` 与 `lib_admin` 正常读写，测试文档删除后总数仍为 3000。

生产化建议：配置服务器至少 3 个（当前单节点只是实验规模）、每个分片扩成 3 节点副本集、mongos 部署 2 个以上并由负载均衡前置、启用 x.509 或 SCRAM-SHA-256、给 `borrow_logs` 设定按年归档策略（用 `$out` 到冷集合，而不是 TTL 删历史数据）。

# 7 问题与总结

## 7.1 五个真实难点与排查过程

**难点一：时间序列集合把历史数据"吃掉"**。最初把 `borrow_logs` 建成时间序列集合，并设了 `expireAfterSeconds: 63072000`（2 年）。老师核对时发现"只能查到 26 条"。排查：`db.borrow_logs.stats()` 显示文档数远小于 3000，`collMod` 查看 `expireAfterSeconds` 命中 2 年窗口，TTL 线程把 2023—2024 的流水全部删除；改为普通集合并去掉过期参数后恢复 3000 条。教训是"保留期要按业务最长的审计要求算"，5 年应为 157680000 秒，而不是拍脑袋写 2 年。

**难点二：分片键索引方向不一致导致 `shardCollection` 失败**。报错 `Please create an index that starts with the proposed shard key before sharding the collection`，但明明有 `{reader_card: 1, borrow_date: -1}` 索引。原因是分片键要求前缀索引的键**模式完全一致**（包括方向），`-1` 与 `+1` 不匹配。补建 `{reader_card: 1, borrow_date: 1}` 后成功。这条规则在文档里只有一句话，踩过一次才记得住。

**难点三：shardsvr 不配 replSetName 直接退出**。启动日志 `BadValue: Cannot start a shardsvr as a standalone server. Please use the option --replSet to start the node as a replica set.`，容器里看起来"进程没起来"，实际是主动拒绝。改为单节点副本集并在配置里写 `replication.replSetName` 后正常。

**难点四：故障转移检测脚本误判"60 秒内未选出新主"**。脚本在 nosql01 上用 `mongosh --port 27102` 轮询，实际连的是本机 127.0.0.1:27102（不存在），一直超时；`print(isWritablePrimary)` 的输出解析也把空行当成结果。改用 `192.168.121.129:27102` 全地址 + pymongo 100 ms 轮询 `hello` 后，测到真实选举耗时 4.9 秒。同时发现重启前必须等旧进程完全退出，否则 dbpath 锁会让新进程立即退出。

**难点五：pymongo 4 的 API 变化**。`Cursor.explain("executionStats")` 在 4.x 只接受关键字参数，报 `TypeError: Cursor.explain() takes 1 positional argument but 2 were given`，改用 `db.command({explain: {...}, verbosity: "executionStats"})`；`db = db or get_db()` 触发 `NotImplementedError: Database objects do not implement truth value testing`，改成 `if db is None`；`MongoClient(readPreference=...)` 的合法关键字是 `read_preference`；`GridFSNoFileError` 实际在 `gridfs.errors.NoFile`。这些问题都不会在静态检查里暴露，只能靠跑通全链路发现。

**额外发现：索引不是越多越好**。Q3 加了 `{status, borrow_date}` 索引后反而从 1.658 ms 变成 2.014 ms。低选择性字段（"已归还"占 71%）上，索引扫描后仍要回表取 20 条完整文档，额外的索引跳转成为净开销。正确做法是用部分索引 `partialFilterExpression: {status: "逾期"}` 只索引少量数据，或者直接依赖 `{borrow_date: -1}` 索引做时间倒序扫描。

**额外发现：验收脚本用错连接账号，把真实馆藏删掉了**。做"只读账号越权被拒"截图时，`verify_reader.js` 里有一条 `deleteOne({isbn: "9787115428028"})` 用来演示"删除被拒绝"。但截图脚本把 `mongosh` 的连接串写成了 `lib_admin`（复制自上一条命令的 `MONGO_STD`），脚本实际以管理员身份执行，`deleteOne` 真的删掉了那本《Python编程：从入门到实践》。表面症状是随后"办理借书"报 `图书不存在：9787115428028`，而 `countDocuments()` 仍是 50 —— 因为越权测试插入的 `TEST-VIOLATE` 文档把数量补回了 50，掩盖了少一本真实图书的事实。定位靠三步：按 ISBN 查不到 → 按标题 `/Python/` 只查到另一本 `Python数据分析` → `audit_logs` 里没有任何 delete 记录（说明不是应用写的）。修复做了三件事：越权脚本的删除目标改成不存在的 `TEST-VIOLATE`，脚本执行完再清理一次，截图脚本改用 `lib_reader` 自己的连接串；同时补了 `reimport_books.py` / `reimport_borrow_logs.py` 两个幂等恢复脚本。教训是**验收脚本必须可重复执行且不产生副作用**，"演示一个失败操作"的语句也要假设它可能会成功。

## 7.2 总结

项目完成了从关系模型到文档模型的迁移：50 册图书、30 位读者、3000 条流水在单机、副本集、分片三种拓扑下都核对一致；11 项检索与 5 组统计全部用聚合管道实现；12 个索引里有 3 条查询提速 1.25—3.11 倍，1 条负优化被如实记录；GridFS 存了 6 个文件并做字节 + MD5 双校验；副本集实测 4.4—4.9 秒完成主备切换且应用零失败；分片集群两片各 1500 条，定向查询比跨分片快约 7 倍。

可改进的方向有三个：一是把 `borrow_logs` 的历史数据按年归档，当前 3000 条规模还看不出压力；二是给统计集合加定时刷新（`$merge` 目前由脚本或菜单触发）；三是把配置服务器与分片扩成三节点副本集，达到生产可用形态。


