"""数据获取器基类"""

import time
import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Callable
from core.models import GachaRecord
from core.config import Config


class BaseFetcher(ABC):
    """抽卡记录获取器基类"""

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

    def close(self):
        """关闭 HTTP 会话，释放连接池"""
        if self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def set_progress_callback(self, callback: Callable):
        """设置进度回调"""
        self._progress_callback = callback

    def _report_progress(self, message: str, progress: float = 0):
        if self._progress_callback:
            self._progress_callback(message, progress)

    def _rate_limit(self):
        """请求限流"""
        interval = self.config.get_request_interval()
        elapsed = time.time() - self._last_request_time
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_request_time = time.time()

    def _request(self, url: str, params: dict = None, headers: dict = None) -> dict:
        """发送请求"""
        self._rate_limit()
        timeout = self.config.get_request_timeout()
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise FetcherError("请求超时，请检查网络连接")
        except requests.exceptions.HTTPError as e:
            raise FetcherError(f"HTTP错误: {e.response.status_code}")
        except requests.exceptions.ConnectionError:
            raise FetcherError("网络连接失败，请检查网络")
        except Exception as e:
            raise FetcherError(f"请求失败: {str(e)}") from e

    @abstractmethod
    def fetch_records(self, url: str = None, account_id: int = None) -> List[GachaRecord]:
        """获取抽卡记录"""
        pass

    @abstractmethod
    def get_game_name(self) -> str:
        pass

    @abstractmethod
    def get_supported_pools(self) -> List[str]:
        pass


class FetcherError(Exception):
    """获取器错误"""
    pass
