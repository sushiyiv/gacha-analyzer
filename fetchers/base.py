"""数据获取器基类：限流、进度回调、统一错误"""

import logging
import time
import requests
from abc import ABC, abstractmethod
from typing import List, Optional, Callable

from core.models import GachaRecord
from core.config import Config

logger = logging.getLogger(__name__)


class FetcherError(Exception):
    pass


class BaseFetcher(ABC):
    def __init__(self):
        self.config = Config()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        self._last_request_time = 0
        self._progress_callback: Optional[Callable] = None
        self._cancel_check: Optional[Callable] = None
        self._detected_uid: str = ""
        self._aborted = False

    def set_progress_callback(self, callback: Callable):
        self._progress_callback = callback

    def abort(self):
        """关闭连接以尽快打断进行中的 HTTP 请求。"""
        self._aborted = True
        try:
            self.session.close()
        except Exception:
            pass

    def _check_cancel(self):
        if self._aborted or (self._cancel_check and self._cancel_check()):
            raise FetcherError("用户取消")

    def _report_progress(self, message: str, progress: float = 0):
        if self._progress_callback:
            self._progress_callback(message, progress)

    def _rate_limit(self):
        if self._aborted:
            raise FetcherError("用户取消")
        interval = self.config.get_request_interval()
        elapsed = time.time() - self._last_request_time
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_request_time = time.time()

    def _request(self, url: str, params: dict = None, headers: dict = None) -> dict:
        self._check_cancel()
        self._rate_limit()
        timeout = (5, self.config.get_request_timeout())
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.error("请求超时")
            raise FetcherError("请求超时，请检查网络连接")
        except requests.exceptions.HTTPError as e:
            logger.error("HTTP错误: %s", e.response.status_code)
            raise FetcherError(f"HTTP错误: {e.response.status_code}")
        except requests.exceptions.ConnectionError:
            if self._aborted:
                raise FetcherError("用户取消")
            logger.error("网络连接失败")
            raise FetcherError("网络连接失败，请检查网络")
        except FetcherError:
            raise
        except Exception as e:
            if self._aborted:
                raise FetcherError("用户取消")
            logger.exception("请求失败")
            raise FetcherError(f"请求失败: {str(e)}")

    @abstractmethod
    def fetch_records(self, url: str = None, account_id: int = None) -> List[GachaRecord]:
        ...

    @abstractmethod
    def get_game_name(self) -> str:
        ...

    @abstractmethod
    def get_supported_pools(self) -> List[str]:
        ...
