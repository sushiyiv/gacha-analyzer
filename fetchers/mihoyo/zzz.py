"""绝区零抽卡记录获取器"""

from typing import List
from fetchers.base import BaseFetcher, FetcherError
from fetchers.mihoyo.api import MihoyoAPI, APIError
from fetchers.cache_reader import CacheReader
from fetchers.url_parser import URLParser
from core.models import GachaRecord


class ZZZFetcher(BaseFetcher):
    """绝区零抽卡记录获取器"""

    def __init__(self):
        super().__init__()
        self.api = MihoyoAPI()
        self.cache = CacheReader()

    def get_game_name(self) -> str:
        return "绝区零"

    def get_supported_pools(self) -> List[str]:
        return ["character", "weapon", "standard"]

    def fetch_records(self, url: str = None, account_id: int = None, latest_time: str = None) -> List[GachaRecord]:
        """获取绝区零抽卡记录"""
        if not url:
            self._report_progress("正在从缓存中提取URL...", 0.1)
            url = self.cache.extract_url("zzz")
            if not url:
                raise FetcherError(
                    "无法自动获取URL。\n\n"
                    "请按以下步骤操作：\n"
                    "1. 打开绝区零\n"
                    "2. 进入调频记录页面\n"
                    "3. 等待记录加载完成\n"
                    "4. 切回本程序，重新点击获取\n\n"
                    "或者手动粘贴调频记录URL。"
                )

        url = URLParser.clean_url(url)
        if not URLParser.validate_url(url):
            raise FetcherError("无效的URL，请检查后重试")

        self._report_progress("正在获取调频记录...", 0.3)

        try:
            raw_records, detected_uid = self.api.fetch_all("zzz", url, self._report_progress, latest_time, cancel_check=self._cancel_check)
        except APIError as e:
            error_msg = str(e)
            if "authkey" in error_msg.lower() or "expired" in error_msg.lower() or "过期" in error_msg:
                raise FetcherError(
                    "authkey已过期。\n\n"
                    "请重新打开绝区零，进入调频记录页面，然后切回本程序重试。"
                )
            raise FetcherError(error_msg)

        self._report_progress("正在解析记录...", 0.8)

        records = []
        for raw in raw_records:
            record = MihoyoAPI.parse_record(raw, "zzz", account_id or 0)
            records.append(record)

        self._detected_uid = detected_uid
        self._report_progress(f"获取完成，共 {len(records)} 条记录", 1.0)
        return records
