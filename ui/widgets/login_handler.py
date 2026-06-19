"""登录处理模块 - 从 import_widget 提取的登录相关逻辑"""

import logging
from PySide6.QtWidgets import QMessageBox, QDialog
from PySide6.QtCore import QTimer

logger = logging.getLogger(__name__)


class LoginHandler:
    """登录获取处理器"""

    def __init__(self, parent_widget, log_func):
        self.widget = parent_widget
        self._log = log_func

    def login_fetch(self, game: str, url_input):
        """登录获取 - 根据游戏打开对应登录窗口"""
        if game == "endfield":
            self.login_endfield(url_input)
        elif game == "arknights":
            self.login_arknights(url_input)
        else:
            QMessageBox.information(self.widget, "提示", "登录获取仅支持终末地和明日方舟。")

    def login_endfield(self, url_input):
        """终末地登录 - API版"""
        try:
            from ui.widgets.login_dialog_api import LoginApiDialog
            dialog = LoginApiDialog(self.widget)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                token = dialog.get_framework_token()
                if token:
                    url_input.setText(token)
                    self._log(f"✓ 终末地登录成功，Token: {token[:20]}...")
                    QTimer.singleShot(100, lambda: self.widget._url_fetch())
                else:
                    self._log("✗ 未获取到凭证")
                    QMessageBox.warning(self.widget, "提示", "未获取到凭证")
            else:
                self._log("登录已取消")
        except Exception as e:
            self._log(f"✗ 登录出错: {type(e).__name__}: {str(e)}")

    def login_arknights(self, url_input):
        """明日方舟登录 - API版"""
        try:
            from ui.widgets.arknights_login_api import ArknightsLoginApiDialog
            dialog = ArknightsLoginApiDialog(self.widget)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                token = dialog.get_token()
                if token:
                    url_input.setText(token)
                    self._log(f"✓ 明日方舟登录成功，Token: {token[:20]}...")
                    QTimer.singleShot(100, lambda: self.widget._url_fetch())
                else:
                    self._log("✗ 未获取到 Token")
                    QMessageBox.warning(self.widget, "提示", "未获取到 Token，请重试。")
            else:
                self._log("登录已取消")
        except Exception as e:
            self._log(f"✗ 登录出错: {type(e).__name__}: {str(e)}")

    @staticmethod
    def get_uid_from_token(game: str, token: str, log_func=None) -> str:
        """通过 token 获取 UID（仅明日方舟和终末地）"""
        log = log_func or (lambda msg: None)

        try:
            import requests as req

            log(f"  正在从Token获取UID... (Token长度: {len(token)})")

            if len(token) < 50:
                log(f"  检测到鹰角账号Token，正在交换...")
                grant_resp = req.post(
                    "https://as.hypergryph.com/user/oauth2/v2/grant",
                    json={"type": 1, "appCode": "be36d44aa36bfb5b", "token": token},
                    timeout=15,
                )
                grant_data = grant_resp.json()
                app_token = grant_data.get("data", {}).get("token")
                if not app_token:
                    log(f"  ✗ 获取app_token失败: {grant_data.get('msg', '未知错误')}")
                    return None

                binding_resp = req.get(
                    "https://binding-api-account-prod.hypergryph.com/account/binding/v1/binding_list",
                    params={"token": app_token, "appCode": game},
                    timeout=15,
                )
                binding_data = binding_resp.json()
                apps = binding_data.get("data", {}).get("list", [])

                for app in apps:
                    if app.get("appCode") == game:
                        for binding in app.get("bindingList", []):
                            uid = binding.get("uid", "")
                            if uid:
                                log(f"  ✓ 获取到UID: {uid}")
                                return str(uid)
                log(f"  ✗ 未找到{game}的绑定角色")
            else:
                log(f"  Token是u8_token（长token），无法直接获取UID")
        except Exception as e:
            log(f"  ✗ 获取UID失败: {str(e)}")
        return None

    @staticmethod
    def update_login_btn_visibility(selected_id, login_btn):
        """根据选择的游戏更新登录按钮的显示状态"""
        show_login = selected_id in ["all", "endfield", "arknights"]
        login_btn.setVisible(show_login)
