# 更新日志

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
