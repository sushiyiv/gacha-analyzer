"""后台获取线程 - 从 import_widget 提取"""

from PySide6.QtCore import QThread, Signal
from fetchers import get_fetcher


class FetchThread(QThread):
    """后台获取抽卡记录的线程"""
    progress = Signal(str, float)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, game, url=None, account_id=None, latest_time=None):
        super().__init__()
        self.game = game
        self.url = url
        self.account_id = account_id
        self.latest_time = latest_time
        self._cancelled = False
        self.detected_uid = ""
        self._fetcher_instance = None

    def cancel(self):
        self._cancelled = True

    def is_cancelled(self):
        return self._cancelled

    def run(self):
        try:
            fetcher = get_fetcher(self.game)
            self._fetcher_instance = fetcher
            fetcher.set_progress_callback(lambda msg, p: self.progress.emit(msg, p))
            fetcher._cancel_check = self.is_cancelled
            records = fetcher.fetch_records(
                url=self.url, account_id=self.account_id, latest_time=self.latest_time
            )
            self.detected_uid = getattr(fetcher, "_detected_uid", "")
            if self._cancelled:
                self.error.emit("用户已取消获取")
            else:
                self.finished.emit(records)
        except Exception as e:
            if self._cancelled:
                self.error.emit("用户已取消获取")
            else:
                self.error.emit(str(e))
