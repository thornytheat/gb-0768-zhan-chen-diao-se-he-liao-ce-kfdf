# 深度登记 展陈调色核料册

- 规模：中型
- 核心规则：按称量时间选皮重，以每次领用、上件和损耗后的实际成分回分剩料，按批号守恒。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 称量记录采信 | 查收件、迟补和票号冲突 | `GET /api/trial/dirty/weighings` | `app/receipts/sheet.py` `app/receipts/tickets.py` | `tests/test_weighings.py` |
| M2 容器皮重匹配 | 核对生效版本与净重 | `GET /api/trial/dirty/tares` | `app/receipts/tare.py` `app/receipts/units.py` | `tests/test_tares.py` |
| M3 颜料批号清分 | 对应别名和规范批号 | `GET /api/trial/dirty/lots` | `app/blend/lots.py` | `tests/test_lots.py` |
| M4 回收料比例重建 | 筛选容器逐票复算回桶成分 | `GET /api/trial/dirty/recovery` | `app/blend/replay.py` `app/blend/share.py` | `tests/test_recovery.py` |
| M5 库存与损耗对账 | 按批号核对存量、损耗与回桶申报 | `GET /api/trial/dirty/balance` | `app/blend/balance.py` `app/blend/claims.py` | `tests/test_balance.py` |
| M8 倒料对账 | 对照出罐票与迟到的收罐票，核在途与短少批号 | `GET /api/trial/pour/transfer` | `app/blend/replay.py` `app/blend/transfer.py` | `tests/test_transfer.py` |
| M6 批次留档复跑 | 封存工单及重跑 | `POST /api/books` | `app/ledger/bookshelf.py` `app/ledger/closeout.py` | `tests/test_history.py` |
| M7 收据证据签发 | 签发可独立复核的成分收据 | `GET /api/export/{key}` | `app/ledger/signoff.py` | `tests/test_receipt.py` |

## 陷阱登记

| TRAP | 现象 | 直接处理的误差 | 处理 | 位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-02 | 秤单带首位 BOM | 票号列识别失败 | 清除 BOM | `app/receipts/sheet.py` | `tests/test_weighings.py::test_bom` |
| TRAP-04 | 段首重复表头 | 表头变一张票 | 单列分段计数 | `app/receipts/sheet.py` | `tests/test_weighings.py::test_repeat_and_input_balance` |
| TRAP-05 | 列数残缺 | 秤字段错位 | 原件行号与原值隔离 | `app/receipts/sheet.py` | `tests/test_weighings.py::test_ragged_row` |
| TRAP-06 | 全角及千分位 | 解析失败 | 归一后以合法格式转重量 | `app/receipts/units.py` | `tests/test_tares.py::test_fullwidth_and_grouping` |
| TRAP-07 | 回桶重量 NULL | 误算为零 | 原值隔离 | `app/receipts/units.py` | `tests/test_tares.py::test_sentinel` |
| TRAP-10 | 分摊小数 | 浮点舍入破坏净重 | 整数毫克与精确余数 | `app/blend/share.py` | `tests/test_recovery.py::test_exact_rounding_residue` |
| TRAP-13 | 迟补回桶票 | 丢票或覆盖后续余额 | 截止前按发生时间入账 | `app/receipts/tickets.py` | `tests/test_weighings.py::test_delayed_return_and_cutoff` |
| TRAP-14 | 同票两种毛重 | 最新行覆盖原值 | 两冲突原件均隔离 | `app/receipts/tickets.py` | `tests/test_weighings.py::test_ticket_conflict` |
| TRAP-15 | g、kg、mg 混用 | 净重差几个数量级 | 转整数毫克 | `app/receipts/units.py` | `tests/test_tares.py::test_mass_units` |
| TRAP-24 | 等余数 | 尾差归属漂移 | 余数相同按批号 | `app/blend/share.py` | `tests/test_recovery.py::test_exact_rounding_residue` |
| TRAP-25 | 两种皮重同时生效 | 误取第一或最后版本 | 双版本保留且隔离 | `app/receipts/tare.py` | `tests/test_tares.py::test_overlapping_tare_versions` |
| TRAP-26 | 收罐票隔班才到 | 原罐虚增可用料，或按出罐量虚记收罐 | 出罐当天扣减，收罐按实收入账 | `app/blend/replay.py` | `tests/test_transfer.py::test_pour_out_deducts_source_on_out_day` |
| TRAP-27 | 实收少于实发 | 短少混进罐存 | 短少按出罐成分拆到批号 | `app/blend/transfer.py` | `tests/test_transfer.py::test_shortage_named_by_lot` |
| TRAP-28 | 收票到达前原罐已补新批号 | 收料成分被重新摊分 | 成分认出罐时点的快照 | `app/blend/replay.py` | `tests/test_transfer.py::test_late_receipt_keeps_out_event_composition` |
| TRAP-29 | 同一收罐票重试 | 收罐重复入账 | 同号去重且同一出罐票只核收一次 | `app/receipts/tickets.py` `app/blend/replay.py` | `tests/test_transfer.py::test_retried_receipt_is_not_booked_twice` |

## 对账规则

- 秤单 40 = 入册 34 + 隔离 5 + 重复表头 1。后续 3 张皮重隔离、2 张批号隔离、1 张超量，回放 28 张。
- 每批号期初 + 领用 + 倒收 = 上件 + 损耗 + 回桶余料 + 倒出 + 争议留罐，倒出减倒收即倒料未收（在途加短少），实收与申报差异另外对照。
- 规则版本与全原件的 SHA-256 构成工单留档键；同目录临时文件写入并同步后，以原子硬链接发布。

## 已知边界

假定单罐均匀混合。同批号出罐来源可追至入罐记录集，分摊只精确到颜料批号；现场结团或挥发需用实测数据补录损耗。留档目录须支持同卷硬链接。
