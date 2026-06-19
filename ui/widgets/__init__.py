# =============================================================================
# ui.widgets 子包的初始化模块
# =============================================================================
# 该文件是 ui.widgets 子包的包初始化文件（package __init__.py）。
# 当其他模块通过 `from ui.widgets import ...` 或 `import ui.widgets` 导入此子包时，
# Python 会首先执行此文件中的代码。
#
# ui.widgets 子包包含以下具体的 widget 模块（均为 PySide6/Qt 窗口部件）：
#   - styled_widgets.py  : 自定义复选框等样式控件
#   - game_list.py       : 游戏/卡池列表组件（支持复选框、拖拽排序）
#   - chart_widget.py    : 图表展示页面
#   - stats_widget.py    : 统计分析页面
#   - home_widget.py     : 总览首页
#   - import_widget.py   : 数据导入页面
#   - manual_add_widget.py : 手动添加页面
#   - settings_widget.py : 设置页面
#   - login_dialog.py    : 登录对话框
#   - login_dialog_api.py : API 登录对话框
#   - login_dialog_light.py : 轻量版登录对话框
#   - arknights_login.py : 明日方舟专用登录界面
#   - arknights_login_api.py : 明日方舟 API 登录界面
#   - arknights_login_light.py : 明日方舟轻量版登录界面
#
# 当前该文件为空，意味着：
#   - ui.widgets 子包不主动导出任何模块
#   - 使用者需要通过完整路径导入，例如：
#       from ui.widgets.game_list import GameListWidget
#       from ui.widgets.chart_widget import ChartWidget
#   - 这样做避免了循环导入问题，因为各 widget 模块之间存在交叉引用
#
# 注意：ui/__init__.py 中的 main_window.py 已通过完整路径导入了这些 widget，
# 因此不需要在此处重复导出。
# =============================================================================
