# 更新日志

## [1.2.0] - 2026-06-19

### 优化
- 拆分 ui/widgets/import_widget.py（1174行）为聚焦模块，降低单文件复杂度：
  - 新增 ui/widgets/file_parser.py：提取文件解析逻辑（JSON/UIGF/小黑盒/CSV/Excel）
  - 新增 ui/widgets/fetch_worker.py：提取后台获取线程 FetchThread
  - 新增 ui/widgets/login_handler.py：提取鹰角账号登录与 Token 获取逻辑
  - import_widget.py 从 1174 行精简至 836 行（-29%），方法从 35 个减少至 25 个
- 新增 ui/helpers.py：提供 make_page_title、make_section_group、make_stat_table 等共享 UI 工厂函数，减少重复的组件创建代码

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
- 支持原神、星穹铁道、绝区零、鸣潮、明日方舟、终末地
- 自动获取、登录获取、手动导入
- 保底分析、统计图表、多账号管理
