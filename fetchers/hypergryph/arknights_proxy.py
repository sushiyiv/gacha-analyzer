"""Arknights local proxy - capture u8_token via hosts hijack + HTTPS server"""

import os
import re
import ssl
import sys
import json
import time
import socket
import signal
import subprocess
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from typing import Optional

# Force UTF-8 output for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        os.system("chcp 65001 >nul 2>&1")


# 配置
TARGET_DOMAIN = "ak-webview.hypergryph.com"
HOSTS_MARKER = "# gacha-analyzer-arknights-proxy"
CERT_DIR = Path(tempfile.gettempdir()) / "gacha_analyzer_certs"
CERT_FILE = CERT_DIR / "server.crt"
KEY_FILE = CERT_DIR / "server.key"
TOKEN_FILE = CERT_DIR / "captured_token.txt"


class TokenCaptureHandler(BaseHTTPRequestHandler):
    """Transparent proxy: capture u8_token, forward request to real server"""

    captured_token = None
    capture_event = threading.Event()

    def _extract_token(self):
        """Extract u8_token from URL params"""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token_list = params.get("u8_token", [])
        if token_list and not TokenCaptureHandler.captured_token:
            token = unquote(token_list[0])
            TokenCaptureHandler.captured_token = token
            TokenCaptureHandler.capture_event.set()
            try:
                TOKEN_FILE.write_text(token, encoding="utf-8")
            except Exception:
                pass

    def _proxy_request(self, method="GET", body=None):
        """Forward request to real server and return response"""
        import urllib.request
        import urllib.error

        self._extract_token()

        real_url = f"https://{TARGET_DOMAIN}{self.path}"
        try:
            req = urllib.request.Request(real_url, method=method)
            # Copy headers
            for key, val in self.headers.items():
                if key.lower() not in ("host", "connection"):
                    req.add_header(key, val)
            if body:
                req.data = body

            # Disable SSL verification for self-signed cert
            import ssl as ssl_mod
            ctx = ssl_mod.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl_mod.CERT_NONE

            resp = urllib.request.urlopen(req, timeout=15, context=ctx)
            resp_data = resp.read()

            self.send_response(resp.status)
            for key, val in resp.getheaders():
                if key.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(resp_data)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h1>502 Proxy Error</h1><p>{e}</p>".encode("utf-8"))

    def do_GET(self):
        self._proxy_request("GET")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else None
        self._proxy_request("POST", body)

    def log_message(self, format, *args):
        pass


def generate_certificate():
    """使用 openssl 生成自签名证书"""
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    if CERT_FILE.exists() and KEY_FILE.exists():
        return True

    openssl_path = "openssl"
    # 检查 openssl 是否可用
    try:
        subprocess.run(
            [openssl_path, "version"],
            capture_output=True, check=True, timeout=5
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        # 尝试 Git 自带的 openssl
        git_openssl = r"D:\Program Files\Git\mingw64\bin\openssl.EXE"
        if os.path.exists(git_openssl):
            openssl_path = git_openssl
        else:
            return False

    try:
        # 生成自签名证书（包含 SAN）
        san_config = f"""[req]
distinguished_name = req_dn
x509_extensions = v3_ext
prompt = no

[req_dn]
CN = {TARGET_DOMAIN}

[v3_ext]
subjectAltName = DNS:{TARGET_DOMAIN}
"""
        config_file = CERT_DIR / "openssl.cnf"
        config_file.write_text(san_config, encoding="utf-8")

        subprocess.run(
            [
                openssl_path, "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(KEY_FILE),
                "-out", str(CERT_FILE),
                "-days", "365", "-nodes",
                "-config", str(config_file),
            ],
            capture_output=True, check=True, timeout=30
        )
        return True
    except subprocess.CalledProcessError:
        return False


def install_certificate():
    """将证书安装到系统信任库（需要管理员权限）"""
    try:
        result = subprocess.run(
            ["certutil", "-addstore", "Root", str(CERT_FILE)],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False


def remove_certificate():
    """从系统信任库移除证书"""
    try:
        # 通过指纹删除
        result = subprocess.run(
            ["certutil", "-delstore", "Root", TARGET_DOMAIN],
            capture_output=True, text=True, timeout=30
        )
        return True
    except Exception:
        return False


def modify_hosts(add=True):
    """修改 hosts 文件"""
    hosts_path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"

    try:
        with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except PermissionError:
        return False, "没有权限修改 hosts 文件，请以管理员身份运行"

    # 移除旧的条目
    lines = content.split("\n")
    lines = [l for l in lines if HOSTS_MARKER not in l]

    if add:
        lines.append(f"127.0.0.1 {TARGET_DOMAIN} {HOSTS_MARKER}")

    new_content = "\n".join(lines)

    try:
        with open(hosts_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_content)
        return True, ""
    except PermissionError:
        return False, "没有权限修改 hosts 文件，请以管理员身份运行"


def flush_dns():
    """刷新 DNS 缓存"""
    try:
        subprocess.run(
            ["ipconfig", "/flushdns"],
            capture_output=True, timeout=10
        )
    except Exception:
        pass


def is_port_available(port):
    """检查端口是否可用"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


def capture_token(timeout=120, progress_callback=None):
    """
    启动本地 HTTPS 服务器捕获 token

    Args:
        timeout: 超时时间（秒）
        progress_callback: 进度回调 (message, progress)

    Returns:
        str: 捕获到的 u8_token，超时返回 None
    """
    def report(msg, prog=0):
        if progress_callback:
            progress_callback(msg, prog)
        else:
            print(f"  {msg}", flush=True)

    # 1. 生成证书
    report("[1/5] 生成SSL证书...", 0.1)
    try:
        if not generate_certificate():
            report("[错误] 证书生成失败，请确保 openssl 可用", 0)
            return None
    except Exception as e:
        report(f"[错误] 证书生成异常: {type(e).__name__}: {e}", 0)
        return None
    report("[1/5] 证书生成成功", 0.15)

    # 2. 安装证书到系统信任库
    report("[2/5] 安装证书到系统信任库...", 0.2)
    try:
        if not install_certificate():
            report("[错误] 证书安装失败", 0)
            return None
    except Exception as e:
        report(f"[错误] 证书安装异常: {type(e).__name__}: {e}", 0)
        return None
    report("[2/5] 证书安装成功", 0.25)

    # 3. 修改 hosts 文件
    report("[3/5] 修改 hosts 文件...", 0.3)
    try:
        ok, err = modify_hosts(add=True)
        if not ok:
            report(f"[错误] hosts 修改失败: {err}", 0)
            return None
    except Exception as e:
        report(f"[错误] hosts 修改异常: {type(e).__name__}: {e}", 0)
        return None
    report("[3/5] hosts 文件已修改", 0.35)

    # 4. 刷新 DNS
    report("[4/5] 刷新 DNS 缓存...", 0.4)
    flush_dns()
    report("[4/5] DNS 已刷新", 0.42)

    # 5. 重置捕获状态
    TokenCaptureHandler.captured_token = None
    TokenCaptureHandler.capture_event.clear()

    # 6. 启动 HTTPS 服务器
    port = 443
    if not is_port_available(port):
        report(f"[错误] 端口 {port} 被占用，请关闭占用端口的程序", 0)
        cleanup()
        return None

    try:
        server = HTTPServer(("0.0.0.0", port), TokenCaptureHandler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(CERT_FILE), str(KEY_FILE))
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    except Exception as e:
        report(f"[错误] HTTPS服务器启动失败: {type(e).__name__}: {e}", 0)
        cleanup()
        return None

    # 在后台线程运行服务器
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    report("[5/5] 代理已就绪，请在游戏内打开「寻访记录」页面", 0.5)
    report(f"等待捕获（{timeout}秒超时）...", 0.5)

    # 7. 等待捕获
    captured = TokenCaptureHandler.capture_event.wait(timeout=timeout)

    # 8. 关闭服务器
    try:
        server.shutdown()
    except Exception:
        pass

    if captured and TokenCaptureHandler.captured_token:
        token = TokenCaptureHandler.captured_token
        report(f"[完成] Token 捕获成功，长度: {len(token)}", 1.0)
        cleanup()
        return token
    else:
        report("[超时] 未捕获到Token，请确保在游戏内打开了寻访记录页面", 0)
        cleanup()
        return None


def cleanup():
    """清理：恢复 hosts 文件"""
    modify_hosts(add=False)
    flush_dns()


def is_admin():
    """检查是否有管理员权限"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


if __name__ == "__main__":
    try:
        print("Arknights Token Capture Proxy", flush=True)
        print("=" * 40, flush=True)

        if not is_admin():
            print("[Error] Need admin privileges", flush=True)
            exit(1)

        print("[OK] Admin confirmed", flush=True)

        def progress(msg, prog):
            print(f"[{prog*100:.0f}%] {msg}", flush=True)

        token = capture_token(timeout=120, progress_callback=progress)
        if token:
            print(f"\n[OK] Token captured, length: {len(token)}", flush=True)
        else:
            print("\n[Failed] Capture failed", flush=True)
    except Exception as e:
        print(f"\n[Exception] {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        exit(1)
