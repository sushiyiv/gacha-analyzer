"""米哈游系列游戏抽卡记录通用获取器"""

from typing import List

from fetchers.base import BaseFetcher, FetcherError
from fetchers.mihoyo.api import MihoyoAPI, APIError
from fetchers.cache_reader import CacheReader
from fetchers.url_parser import URLParser
from core.models import GachaRecord


class MihoyoGachaFetcher(BaseFetcher):
    """米哈游系列抽卡记录获取器基类

    子类只需提供游戏标识、显示名、支持卡池、缓存 key 和错误提示即可。
    """

    game_key: str = ""
    game_name: str = ""
    supported_pools: List[str] = []
    cache_game_key: str = ""

    url_missing_tip: str = ""
    expired_tip: str = ""

    def __init__(self):
        super().__init__()
        self.api = MihoyoAPI()
        self.cache = CacheReader()

    def get_game_name(self) -> str:
        return self.game_name

    def get_supported_pools(self) -> List[str]:
        return list(self.supported_pools)

    def fetch_records(self, url: str = None, account_id: int = None, latest_time: str = None) -> List[GachaRecord]:
        if not url:
            self._report_progress("正在从缓存中提取URL...", 0.1)
            url = self.cache.extract_url(self.cache_game_key)
            if not url:
                raise FetcherError(
                    "无法自动获取URL。\n\n"
                    "请按以下步骤操作：\n"
                    f"{self.url_missing_tip}\n\n"
                    "或者手动粘贴抽卡记录URL。"
                )

        url = URLParser.clean_url(url)
        if not URLParser.validate_url(url):
            raise FetcherError("无效的URL，请检查后重试")

        self._report_progress("正在获取抽卡记录...", 0.3)

        try:
            raw_records, detected_uid = self.api.fetch_all(
                self.game_key,
                url,
                self._report_progress,
                latest_time,
                cancel_check=self._cancel_check,
            )
        except APIError as e:
            error_msg = str(e)
            if any(keyword in error_msg.lower() for keyword in ["authkey", "expired", "过期"]):
                raise FetcherError(self.expired_tip or f"authkey 已过期，请重新获取。\n原始信息：{error_msg}")
            raise FetcherError(error_msg)

        self._report_progress("正在解析记录...", 0.8)

        records = []
        for raw in raw_records:
            record = MihoyoAPI.parse_record(raw, self.game_key, account_id or 0)
            records.append(record)

        self._detected_uid = detected_uid
        self._report_progress(f"获取完成，共 {len(records)} 条记录", 1.0)
        return records
