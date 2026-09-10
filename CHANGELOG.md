# 更新日志

## [1.2.3] - 2026-09-10
### Fixed
- 修正保底分析 `current_rate` / 概率曲线 off-by-one（下一抽编号应为 `current_pity + 1`）
- 修正限定期望公式：小保底赢率 p 下为 `E*(2-p)`，武器池 75/25 不再用错误的 `E/p`
- 运势评分理论期望改用含软保底的解析期望，不再用 `1/base_rate`
- 通用 JSON/CSV/Excel 导入为每条记录生成稳定 `item_id`，避免 UNIQUE 约束只入库 1 条
- 小黑盒导入按卡池名映射真实 `pool_type`，同秒多条用序号区分 `item_id`
- 导出 JSON 补充 `item_id`，支持安全回导去重
- 数据库备份改用 `sqlite3.Connection.backup()`，WAL 模式下不再丢最近提交
- 恢复时清理残留 `-wal` / `-shm` 文件
- 打包遗漏 QSS 导致侧栏未选中项几乎不可见
- 打包版用户数据改存 exe 同级 `data/`，`build.py` 重建时自动保留
- 真增量获取：有 `latest_time` 时提前停止翻页并只保留更新记录
- 卡池翻页安全上限 100 → 500，触顶时明确警告
- 启动时按 `schema_version` 决定是否全量重算保底，不再每次扫全表
- `Config.save()` 只写相对默认值/全局配置有差异的用户键

### Added
- 恢复核心单元测试：`tests/test_analyzer.py`、`tests/test_database.py`、`tests/test_models.py`

### Removed
- 删除未使用的遗留模块：`gacha_engine.py`、`simulator.py`、`pity_analyzer.py`、`history.py`、`banner_config.py`
- 清理 core/fetchers/ui 中解释基础语法的冗长注释

## [1.2.1] - 2026-08-14
### Fixed
- 修复绝区零邦布卡池保底计数不准确的问题（API gacha_type映射错误）
- 修复绝区零邦布3★音擎被错误分类到特殊音擎池的问题
- 修正"每UP需"算法：使用限定池所有五星的保底计数总和除以UP五星数
- 修正"平均出金"算法：使用所有五星的保底计数之和除以五星数
- 邦布频段显示"邦布数"统计
- 常驻池/新手池显示"金数"统计
- 独家重映/音擎回响使用和限定池相同的统计显示

## [1.2.0] - 2026-08-09

### 移除
- 移除明日方舟 (Arknights) 和终末地 (Endfield) 全部支持（27+ 文件，约 5200 行）
- 移除测试用例目录 `tests/`

### 修复
- 修复星铁联动池角色（远坂凛等）被错误判定为非限定的问题
- 为星铁所有卡池类型（含联动池）补充 UP 角色判断

### 优化
- 为所有关键路径的异常处理补充日志记录（`logger.error`/`logger.exception`）
- 添加全局异常钩子（`sys.excepthook` + Qt 消息处理器），捕获未处理异常

## [1.1.0] - 2026-06-03

### 新增
- 许可证文件（MIT - 禁止未授权商用）
- 统一日志配置模块 `core/logging_config.py`
- 核心单元测试：`tests/test_analyzer.py`、`tests/test_database.py`、`tests/test_models.py`、`tests/test_config.py`
- 贡献指南 `CONTRIBUTING.md`
- 更新日志 `CHANGELOG.md`

### 优化
- 米哈游抓取层重构：抽取 `fetchers/mihoyo/base.py` 通用基类，减少代码重复
- `core/config.py`：增加默认值兜底、类型安全读取、目录自动初始化
- `core/database.py`：优化连接管理、迁移防护、上下文连接器、日志可追踪性
- `ui/main_window.py`：替换 print 为 logging，减少重复初始化和 UI 重建抖动
- 替换各 fetcher 中的 `print` 调试为 `logging` 标准日志
- `.gitignore`：完善虚拟环境、编辑器、日志等忽略规则
- `README.md`：补齐徽章、隐私声明、许可证说明

### 修复
- README 代码块格式错误（反引号渲染异常）
- `main_window.py` 中重复 `addStretch` 导致布局冗余

## [1.0.0] - 2026-05-28

### 初始版本
- 支持原神、星穹铁道、绝区零、鸣潮
- 自动获取、登录获取、手动导入
- 保底分析、统计图表、多账号管理
