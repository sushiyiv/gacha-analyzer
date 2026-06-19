"""明日方舟本地代理服务器 - 通过 hosts 劫持 + HTTPS 服务器捕获 u8_token

本模块实现了一个透明代理服务器，用于捕获明日方舟游戏客户端的 u8_token。

工作原理:
    1. 生成自签名 SSL 证书（用于 HTTPS 解密）
    2. 将证书安装到系统信任库（避免浏览器/客户端警告）
    3. 修改 hosts 文件，将 ak-webview.hypergryph.com 指向 127.0.0.1
    4. 启动 HTTPS 服务器监听 443 端口
    5. 拦截游戏客户端的请求，提取 u8_token
    6. 将请求转发到真实服务器，返回响应

安全说明:
    - 证书仅安装在本地系统信任库，不影响其他设备
    - 代理仅在程序运行期间生效
    - 程序退出时会自动清理 hosts 文件
    - 所有转发的请求保持原始 headers 和 body

使用场景:
    - 当用户无法通过日志文件获取 u8_token 时
    - 当用户无法访问鹰角官网登录时
    - 需要实时捕获游戏客户端的 token 时

注意:
    - 需要管理员权限才能修改 hosts 文件和安装证书
    - 需要 openssl 工具生成证书（Git for Windows 自带）
    - 端口 443 可能被其他程序占用（如 IIS、Apache）

作者: gacha-analyzer 开发团队
"""

import os  # 操作系统接口，用于环境变量、系统命令等
import re  # 正则表达式（备用导入）
import ssl  # SSL/TLS 模块，用于创建 HTTPS 服务器
import sys  # Python 解释器相关变量
import json  # JSON 序列化/反序列化（备用导入）
import time  # 时间模块（备用导入）
import socket  # 套接字模块，用于检查端口可用性
import signal  # 信号处理模块（备用导入）
import subprocess  # 子进程模块，用于执行系统命令
import tempfile  # 临时目录模块，用于存储证书文件
import threading  # 线程模块，用于在后台运行服务器
from http.server import HTTPServer, BaseHTTPRequestHandler  # HTTP 服务器基类
from pathlib import Path  # 路径处理模块
from urllib.parse import urlparse, parse_qs, unquote  # URL 解析和解码
from typing import Optional  # 类型提示

# ========== 强制 Windows 控制台使用 UTF-8 编码 ==========
# Windows 默认使用 GBK 编码，可能导致中文输出乱码
# 这段代码确保控制台输出使用 UTF-8 编码
if sys.platform == "win32":
    try:
        # Python 3.7+ 支持 reconfigure 方法
        # encoding="utf-8" 设置编码为 UTF-8
        # errors="replace" 遇到无法编码的字符时用 ? 替代
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        # 如果 reconfigure 不可用（Python < 3.7）
        # 使用 chcp 命令切换控制台代码页到 65001 (UTF-8)
        # >nul 2>&1 隐藏输出
        os.system("chcp 65001 >nul 2>&1")


# ========== 全局配置常量 ==========

# 目标域名：明日方舟 Webview 服务器
# 所有指向此域名的请求都会被本地代理拦截
TARGET_DOMAIN = "ak-webview.hypergryph.com"

# hosts 文件标记：用于识别本程序添加的条目
# 格式: # gacha-analyzer-arknights-proxy
# 使用唯一标记避免误删其他程序的 hosts 条目
HOSTS_MARKER = "# gacha-analyzer-arknights-proxy"

# 证书存储目录：使用系统临时目录
# 路径示例: C:\Users\username\AppData\Local\Temp\gacha_analyzer_certs
CERT_DIR = Path(tempfile.gettempdir()) / "gacha_analyzer_certs"

# 证书文件路径
CERT_FILE = CERT_DIR / "server.crt"  # 自签名证书
KEY_FILE = CERT_DIR / "server.key"  # 私钥文件

# 捕获的 token 存储路径
TOKEN_FILE = CERT_DIR / "captured_token.txt"


class TokenCaptureHandler(BaseHTTPRequestHandler):
    """透明代理处理器：捕获 u8_token，转发请求到真实服务器

    继承自 BaseHTTPRequestHandler，重写请求处理方法。
    主要功能：
    1. 从请求 URL 中提取 u8_token
    2. 将请求转发到真实服务器
    3. 将响应返回给客户端

    类属性:
        captured_token: 捕获到的 u8_token（类级别共享）
        capture_event: 线程事件，用于通知主程序 token 已捕获

    工作流程:
        1. 客户端（游戏）发起 HTTPS 请求
        2. 请求被本地 443 端口接收
        3. 提取 URL 中的 u8_token 参数
        4. 将请求转发到真实服务器（https://ak-webview.hypergryph.com）
        5. 将真实服务器的响应返回给客户端
        6. 客户端完全无感知（透明代理）
    """

    # 类级别变量：捕获到的 token
    # 使用类变量而非实例变量，因为所有请求共享同一个 token
    captured_token = None

    # 类级别事件：用于通知主程序 token 已捕获
    # Event 对象支持 wait() 和 set() 方法
    # 主程序调用 wait() 阻塞等待，代理调用 set() 通知
    capture_event = threading.Event()

    def _extract_token(self):
        """从请求 URL 参数中提取 u8_token

        URL 格式示例:
            https://ak-webview.hypergryph.com/gacha?u8_token=xxx&other=yyy

        提取逻辑:
            1. 解析 URL 路径和查询参数
            2. 从查询参数中提取 u8_token
            3. 如果尚未捕获过 token，则保存
            4. 触发捕获事件，通知主程序
            5. 将 token 写入文件（备份）
        """
        # 解析 URL
        # urlparse 将 URL 分解为: scheme, netloc, path, params, query, fragment
        # 例如: "https://example.com/path?a=1&b=2" -> query="a=1&b=2"
        parsed = urlparse(self.path)

        # 解析查询参数
        # parse_qs 将查询字符串转换为字典
        # 例如: "a=1&b=2" -> {"a": ["1"], "b": ["2"]}
        # 注意：值是列表，因为同一个参数可能出现多次
        params = parse_qs(parsed.query)

        # 提取 u8_token 参数
        token_list = params.get("u8_token", [])

        # 检查条件:
        # 1. token_list 非空（URL 中包含 u8_token）
        # 2. 尚未捕获过 token（避免重复捕获）
        if token_list and not TokenCaptureHandler.captured_token:
            # unquote 解码 URL 编码的字符（如 %2F -> /）
            token = unquote(token_list[0])

            # 保存到类变量
            TokenCaptureHandler.captured_token = token

            # 触发捕获事件
            # set() 方法会唤醒所有等待的线程
            TokenCaptureHandler.capture_event.set()

            try:
                # 将 token 写入文件（备份）
                # write_text 写入字符串并自动关闭文件
                TOKEN_FILE.write_text(token, encoding="utf-8")
            except Exception:
                # 写入失败不影响主流程（文件可能被占用）
                pass

    def _proxy_request(self, method="GET", body=None):
        """将请求转发到真实服务器并返回响应

        参数:
            method (str): HTTP 方法（GET、POST 等）
            body (bytes, optional): 请求体（POST 请求时使用）

        工作流程:
            1. 提取 URL 中的 u8_token
            2. 构造真实服务器的 URL
            3. 复制客户端的 headers
            4. 发送请求到真实服务器
            5. 将响应返回给客户端

        异常处理:
            - HTTPError: 服务器返回错误状态码（4xx、5xx）
            - Exception: 网络错误、超时等其他异常

        注意:
            - 使用 urllib.request 而非 requests，避免额外依赖
            - SSL 验证被禁用，因为使用自签名证书
            - 超时设置为 15 秒
        """
        # 延迟导入，避免模块加载时就导入
        import urllib.request
        import urllib.error

        # 第一步：提取 u8_token
        self._extract_token()

        # 构造真实服务器的 URL
        # 保留原始的路径和查询参数
        real_url = f"https://{TARGET_DOMAIN}{self.path}"

        try:
            # 创建请求对象
            # method 参数指定 HTTP 方法
            req = urllib.request.Request(real_url, method=method)

            # 复制客户端的 headers
            # 遍历所有 headers，排除 host 和 connection
            # host: 需要使用真实域名
            # connection: 由 urllib 自动管理
            for key, val in self.headers.items():
                if key.lower() not in ("host", "connection"):
                    req.add_header(key, val)

            # 如果有请求体（POST 请求），添加到请求中
            if body:
                req.data = body

            # ========== 配置 SSL 上下文 ==========
            # 创建默认 SSL 上下文
            import ssl as ssl_mod
            ctx = ssl_mod.create_default_context()

            # 禁用主机名验证
            # 因为使用自签名证书，证书中的域名可能不匹配
            ctx.check_hostname = False

            # 禁用证书验证
            # 自签名证书不在系统信任库中，需要跳过验证
            ctx.verify_mode = ssl_mod.CERT_NONE

            # 发送请求到真实服务器
            # timeout=15 设置超时 15 秒
            # context 参数传入配置好的 SSL 上下文
            resp = urllib.request.urlopen(req, timeout=15, context=ctx)

            # 读取响应数据
            resp_data = resp.read()

            # ========== 返回响应给客户端 ==========
            # 发送 HTTP 状态码
            self.send_response(resp.status)

            # 复制响应 headers
            # 排除 transfer-encoding 和 connection
            # transfer-encoding: 分块传输由服务器处理
            # connection: 连接管理由服务器处理
            for key, val in resp.getheaders():
                if key.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(key, val)

            # 发送 headers 结束标记
            self.end_headers()

            # 发送响应体
            self.wfile.write(resp_data)

        except urllib.error.HTTPError as e:
            # 服务器返回错误状态码（4xx、5xx）
            # 发送错误状态码给客户端
            self.send_response(e.code)

            # 发送错误页面
            self.send_header("Content-Type", "text/html")
            self.end_headers()

            # 将服务器返回的错误页面转发给客户端
            self.wfile.write(e.read())

        except Exception as e:
            # 其他异常：网络错误、超时、DNS 解析失败等
            # 发送 502 Bad Gateway 错误
            self.send_response(502)

            # 发送错误页面（包含异常信息）
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()

            # 构造简单的错误页面
            # 使用 UTF-8 编码确保中文正常显示
            self.wfile.write(f"<h1>502 Proxy Error</h1><p>{e}</p>".encode("utf-8"))

    def do_GET(self):
        """处理 GET 请求

        当客户端发送 GET 请求时，BaseHTTPRequestHandler 会自动调用此方法。
        例如: GET /gacha?u8_token=xxx HTTP/1.1

        实现:
            直接调用 _proxy_request 方法，传入 GET 方法名。
        """
        self._proxy_request("GET")

    def do_POST(self):
        """处理 POST 请求

        当客户端发送 POST 请求时，BaseHTTPRequestHandler 会自动调用此方法。
        例如: POST /api/xxx HTTP/1.1 Content-Length: 100 ...

        实现:
            1. 从 Content-Length header 读取请求体长度
            2. 读取请求体
            3. 调用 _proxy_request 方法，传入 POST 方法名和请求体
        """
        # 从 headers 中获取请求体长度
        # 默认值为 0（如果没有 Content-Length header）
        length = int(self.headers.get("Content-Length", 0))

        # 读取请求体
        # rfile 是输入流，read(length) 读取指定长度的字节
        # 如果长度为 0 或负数，返回 None
        body = self.rfile.read(length) if length > 0 else None

        # 转发 POST 请求
        self._proxy_request("POST", body)

    def log_message(self, format, *args):
        """禁用默认的日志输出

        BaseHTTPRequestHandler 默认会将每个请求打印到控制台。
        为了减少日志噪音，我们重写此方法为空操作。

        参数:
            format (str): 日志格式字符串
            *args: 格式化参数
        """
        pass


def generate_certificate():
    """使用 openssl 生成自签名 SSL 证书

    生成的证书用于 HTTPS 服务器，使游戏客户端能够建立 TLS 连接。

    证书信息:
        - 主体: CN=ak-webview.hypergryph.com
        - SAN: DNS:ak-webview.hypergryph.com
        - 有效期: 365 天
        - 密钥类型: RSA 2048 位
        - 无密码保护 (-nodes)

    文件位置:
        - 证书: {TEMP}/gacha_analyzer_certs/server.crt
        - 私钥: {TEMP}/gacha_analyzer_certs/server.key

    返回:
        bool: 证书生成成功返回 True，失败返回 False

    依赖:
        - openssl 命令行工具
        - Git for Windows 自带的 openssl（备用）

    异常处理:
        - FileNotFoundError: openssl 不存在
        - CalledProcessError: openssl 执行失败
        - 其他异常被捕获并返回 False
    """
    # 创建证书存储目录
    # parents=True 递归创建父目录
    # exist_ok=True 如果目录已存在不报错
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    # 检查证书文件是否已存在
    # 如果存在，直接返回 True，避免重复生成
    if CERT_FILE.exists() and KEY_FILE.exists():
        return True

    # openssl 命令行工具的路径
    openssl_path = "openssl"

    # 检查 openssl 是否可用
    try:
        # 执行 openssl version 命令
        # capture_output=True 捕获输出
        # check=True 如果返回码非零则抛出异常
        # timeout=5 设置超时 5 秒
        subprocess.run(
            [openssl_path, "version"],
            capture_output=True, check=True, timeout=5
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        # openssl 不在系统 PATH 中
        # 尝试 Git for Windows 自带的 openssl
        git_openssl = r"D:\Program Files\Git\mingw64\bin\openssl.EXE"
        if os.path.exists(git_openssl):
            # 找到 Git 自带的 openssl，使用它
            openssl_path = git_openssl
        else:
            # 未找到 openssl，返回失败
            return False

    try:
        # ========== 生成自签名证书（包含 SAN） ==========
        # SAN (Subject Alternative Name) 是现代浏览器要求的
        # 证书必须包含 SAN，否则会报错

        # OpenSSL 配置文件内容
        # 使用 f-string 插入目标域名
        san_config = f"""[req]
distinguished_name = req_dn
x509_extensions = v3_ext
prompt = no

[req_dn]
CN = {TARGET_DOMAIN}

[v3_ext]
subjectAltName = DNS:{TARGET_DOMAIN}
"""
        # 写入配置文件
        config_file = CERT_DIR / "openssl.cnf"
        config_file.write_text(san_config, encoding="utf-8")

        # 执行 openssl 命令生成证书
        # 命令参数说明:
        # - req: 创建证书签名请求
        # - -x509: 直接生成自签名证书（而非 CSR）
        # - -newkey rsa:2048: 生成 2048 位 RSA 密钥
        # - -keyout: 指定私钥输出文件
        # - -out: 指定证书输出文件
        # - -days 365: 证书有效期 365 天
        # - -nodes: 不加密私钥（无密码保护）
        # - -config: 使用自定义配置文件
        subprocess.run(
            [
                openssl_path, "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(KEY_FILE),  # 私钥输出路径
                "-out", str(CERT_FILE),  # 证书输出路径
                "-days", "365",  # 有效期 365 天
                "-nodes",  # 不加密私钥
                "-config", str(config_file),  # 配置文件路径
            ],
            capture_output=True,  # 捕获输出
            check=True,  # 检查返回码
            timeout=30  # 超时 30 秒
        )

        # 证书生成成功
        return True

    except subprocess.CalledProcessError:
        # openssl 执行失败（返回码非零）
        # 可能原因：配置文件格式错误、权限不足等
        return False


def install_certificate():
    """将证书安装到系统信任库（需要管理员权限）

    使用 Windows 的 certutil 工具将自签名证书添加到根证书信任库。
    这样游戏客户端就不会因为证书不可信而拒绝连接。

    命令: certutil -addstore Root <证书文件>

    返回:
        bool: 安装成功返回 True，失败返回 False

    注意:
        - 需要管理员权限
        - 如果证书已存在，certutil 会自动覆盖
        - 证书存储在: LocalMachine\Root（系统级信任库）
    """
    try:
        # 执行 certutil 命令安装证书
        # -addstore: 添加证书到存储
        # Root: 根证书信任库
        # str(CERT_FILE): 证书文件路径
        result = subprocess.run(
            ["certutil", "-addstore", "Root", str(CERT_FILE)],
            capture_output=True,  # 捕获输出
            text=True,  # 将输出作为字符串（而非字节）
            timeout=30  # 超时 30 秒
        )

        # 检查返回码
        # 0 表示成功，非 0 表示失败
        return result.returncode == 0

    except Exception:
        # 执行失败（权限不足、certutil 不存在等）
        return False


def remove_certificate():
    """从系统信任库移除证书

    使用 certutil 工具从根证书信任库删除本程序安装的证书。
    在程序退出时调用，清理系统状态。

    命令: certutil -delstore Root <域名>

    返回:
        bool: 删除成功返回 True，失败返回 False

    注意:
        - 需要管理员权限
        - 通过域名删除，因为证书是按域名存储的
        - 如果证书不存在，certutil 会返回错误
    """
    try:
        # 执行 certutil 命令删除证书
        # -delstore: 从存储删除证书
        # Root: 根证书信任库
        # TARGET_DOMAIN: 要删除的证书域名
        result = subprocess.run(
            ["certutil", "-delstore", "Root", TARGET_DOMAIN],
            capture_output=True,
            text=True,
            timeout=30
        )

        # 无论成功与否都返回 True
        # 因为删除不存在的证书也不算错误
        return True

    except Exception:
        # 执行失败（权限不足、certutil 不存在等）
        return False


def modify_hosts(add=True):
    """修改 Windows hosts 文件

    hosts 文件用于将域名映射到 IP 地址。
    本函数将 ak-webview.hypergryph.com 指向 127.0.0.1（本地），
    使游戏客户端的请求被本地代理服务器接收。

    文件路径: C:\Windows\System32\drivers\etc\hosts

    参数:
        add (bool): True 添加条目，False 移除条目

    返回:
        tuple: (success: bool, error_message: str)
            - success: 操作是否成功
            - error_message: 失败时的错误信息

    实现逻辑:
        1. 读取 hosts 文件
        2. 移除旧的条目（如果存在）
        3. 如果 add=True，添加新条目
        4. 写回 hosts 文件

    异常处理:
        - PermissionError: 权限不足（需要管理员权限）

    注意:
        - 每次修改前先清理旧条目，避免重复
        - 使用换行符 \n 而非 \r\n（Windows 换行符）
        - 标记字符串用于识别本程序添加的条目
    """
    # 构造 hosts 文件路径
    hosts_path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"

    try:
        # 读取 hosts 文件内容
        with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except PermissionError:
        # 权限不足，返回错误信息
        return False, "没有权限修改 hosts 文件，请以管理员身份运行"

    # ========== 移除旧的条目 ==========
    # 按行分割
    lines = content.split("\n")

    # 过滤掉包含标记的行
    lines = [l for l in lines if HOSTS_MARKER not in l]

    # ========== 添加新条目（如果需要） ==========
    if add:
        # 格式: 127.0.0.1 域名 # 标记
        # 127.0.0.1: 指向本地
        # 标记: 用于识别和清理
        lines.append(f"127.0.0.1 {TARGET_DOMAIN} {HOSTS_MARKER}")

    # 重新组合为字符串
    new_content = "\n".join(lines)

    try:
        # 写回 hosts 文件
        # encoding="utf-8": 使用 UTF-8 编码
        # newline="\n": 使用 Unix 换行符（避免 \r\n）
        with open(hosts_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_content)

        # 操作成功
        return True, ""

    except PermissionError:
        # 写入失败，返回错误信息
        return False, "没有权限修改 hosts 文件，请以管理员身份运行"


def flush_dns():
    """刷新 Windows DNS 缓存

    修改 hosts 文件后，需要刷新 DNS 缓存才能使修改生效。
    否则系统可能仍使用旧的 DNS 缓存。

    命令: ipconfig /flushdns

    异常处理:
        所有异常都被捕获并静默处理。
        刷新失败不会影响主流程。
    """
    try:
        # 执行 ipconfig /flushdns 命令
        subprocess.run(
            ["ipconfig", "/flushdns"],
            capture_output=True,  # 捕获输出（不打印到控制台）
            timeout=10  # 超时 10 秒
        )
    except Exception:
        # 执行失败，静默处理
        # 可能原因：非 Windows 系统、ipconfig 不存在等
        pass


def is_port_available(port):
    """检查指定端口是否可用

    在启动 HTTPS 服务器前，需要检查 443 端口是否被占用。
    如果端口已被占用（如 IIS、Apache 等），服务器无法启动。

    参数:
        port (int): 要检查的端口号

    返回:
        bool: 端口可用返回 True，被占用返回 False

    实现原理:
        尝试绑定 (bind) 到指定端口
        - 成功: 端口可用
        - 失败 (OSError): 端口被占用
    """
    try:
        # 创建 TCP 套接字
        # AF_INET: IPv4
        # SOCK_STREAM: TCP
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # 尝试绑定到 127.0.0.1（本地回环地址）
            # 如果绑定成功，说明端口可用
            # 如果抛出 OSError，说明端口被占用
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        # 端口被占用
        return False


def capture_token(timeout=120, progress_callback=None):
    """启动本地 HTTPS 服务器捕获 u8_token

    这是本模块的主函数，协调整个 token 捕获流程。

    参数:
        timeout (int): 等待捕获的超时时间（秒），默认 120 秒
        progress_callback (callable, optional): 进度回调函数
            签名: callback(message: str, progress: float)
            - message: 当前状态描述
            - progress: 进度百分比（0.0 - 1.0）

    返回:
        str: 捕获到的 u8_token，超时或失败返回 None

    流程说明:
        1. 生成 SSL 证书
        2. 安装证书到系统信任库
        3. 修改 hosts 文件
        4. 刷新 DNS 缓存
        5. 重置捕获状态
        6. 启动 HTTPS 服务器
        7. 等待游戏客户端连接并捕获 token
        8. 关闭服务器，清理资源

    使用示例:
        def progress(msg, prog):
            print(f"[{prog*100:.0f}%] {msg}")

        token = capture_token(timeout=120, progress_callback=progress)
        if token:
            print(f"Token: {token}")
        else:
            print("捕获超时")

    注意:
        - 需要管理员权限
        - 需要 openssl 工具
        - 端口 443 必须可用
    """
    # 内部进度报告函数
    # 如果提供了回调函数，使用回调；否则打印到控制台
    def report(msg, prog=0):
        if progress_callback:
            progress_callback(msg, prog)
        else:
            print(f"  {msg}", flush=True)

    # ========== 步骤 1: 生成 SSL 证书 ==========
    report("[1/5] 生成SSL证书...", 0.1)
    try:
        if not generate_certificate():
            # 证书生成失败
            report("[错误] 证书生成失败，请确保 openssl 可用", 0)
            return None
    except Exception as e:
        # 证书生成异常
        report(f"[错误] 证书生成异常: {type(e).__name__}: {e}", 0)
        return None
    report("[1/5] 证书生成成功", 0.15)

    # ========== 步骤 2: 安装证书到系统信任库 ==========
    report("[2/5] 安装证书到系统信任库...", 0.2)
    try:
        if not install_certificate():
            # 证书安装失败
            report("[错误] 证书安装失败", 0)
            return None
    except Exception as e:
        # 证书安装异常
        report(f"[错误] 证书安装异常: {type(e).__name__}: {e}", 0)
        return None
    report("[2/5] 证书安装成功", 0.25)

    # ========== 步骤 3: 修改 hosts 文件 ==========
    report("[3/5] 修改 hosts 文件...", 0.3)
    try:
        ok, err = modify_hosts(add=True)
        if not ok:
            # hosts 修改失败
            report(f"[错误] hosts 修改失败: {err}", 0)
            return None
    except Exception as e:
        # hosts 修改异常
        report(f"[错误] hosts 修改异常: {type(e).__name__}: {e}", 0)
        return None
    report("[3/5] hosts 文件已修改", 0.35)

    # ========== 步骤 4: 刷新 DNS 缓存 ==========
    report("[4/5] 刷新 DNS 缓存...", 0.4)
    flush_dns()
    report("[4/5] DNS 已刷新", 0.42)

    # ========== 步骤 5: 重置捕获状态 ==========
    # 清空之前可能存在的 token
    TokenCaptureHandler.captured_token = None

    # 清除事件状态，确保 wait() 能够正确等待
    TokenCaptureHandler.capture_event.clear()

    # ========== 步骤 6: 启动 HTTPS 服务器 ==========
    port = 443  # HTTPS 默认端口

    # 检查端口是否可用
    if not is_port_available(port):
        report(f"[错误] 端口 {port} 被占用，请关闭占用端口的程序", 0)
        cleanup()
        return None

    try:
        # 创建 HTTP 服务器
        # ("0.0.0.0", port): 监听所有网络接口的指定端口
        # TokenCaptureHandler: 请求处理器类
        server = HTTPServer(("0.0.0.0", port), TokenCaptureHandler)

        # 创建 SSL 上下文
        # PROTOCOL_TLS_SERVER: 使用服务器端 TLS 协议
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

        # 加载证书和私钥
        ctx.load_cert_chain(str(CERT_FILE), str(KEY_FILE))

        # 将 SSL 上下文包装到服务器套接字
        # wrap_socket 将普通 TCP 套接字转换为 SSL 套接字
        # server_side=True 表示这是服务器端（使用服务器证书）
        server.socket = ctx.wrap_socket(server.socket, server_side=True)

    except Exception as e:
        # 服务器启动失败
        report(f"[错误] HTTPS服务器启动失败: {type(e).__name__}: {e}", 0)
        cleanup()
        return None

    # 在后台线程运行服务器
    # daemon=True: 主线程退出时，子线程自动退出
    # serve_forever: 无限循环处理请求
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # 报告服务器已就绪
    report("[5/5] 代理已就绪，请在游戏内打开「寻访记录」页面", 0.5)
    report(f"等待捕获（{timeout}秒超时）...", 0.5)

    # ========== 步骤 7: 等待捕获 ==========
    # capture_event.wait(timeout) 阻塞等待
    # 返回 True: 事件被触发（token 已捕获）
    # 返回 False: 超时（未捕获到 token）
    captured = TokenCaptureHandler.capture_event.wait(timeout=timeout)

    # ========== 步骤 8: 关闭服务器 ==========
    try:
        # 优雅关闭服务器
        # shutdown() 会等待当前请求处理完成
        server.shutdown()
    except Exception:
        # 关闭失败，静默处理
        pass

    # ========== 返回结果 ==========
    if captured and TokenCaptureHandler.captured_token:
        # 成功捕获到 token
        token = TokenCaptureHandler.captured_token
        report(f"[完成] Token 捕获成功，长度: {len(token)}", 1.0)

        # 清理 hosts 文件
        cleanup()

        # 返回捕获到的 token
        return token
    else:
        # 超时或未捕获到 token
        report("[超时] 未捕获到Token，请确保在游戏内打开了寻访记录页面", 0)

        # 清理 hosts 文件
        cleanup()

        # 返回 None 表示失败
        return None


def cleanup():
    """清理函数：恢复 hosts 文件并刷新 DNS

    在程序退出或捕获失败时调用，恢复系统状态。
    主要操作：
    1. 移除 hosts 文件中的代理条目
    2. 刷新 DNS 缓存

    注意：
        此函数应该在程序退出前调用
        即使清理失败，也不会影响其他功能
    """
    # 移除 hosts 条目（add=False）
    modify_hosts(add=False)

    # 刷新 DNS 缓存
    flush_dns()


def is_admin():
    """检查当前程序是否以管理员权限运行

    修改 hosts 文件和安装证书需要管理员权限。
    此函数用于在启动时检查权限，提前给出提示。

    返回:
        bool: 以管理员权限运行返回 True，否则返回 False

    实现原理:
        使用 Windows API shell32.IsUserAnAdmin()
        - 返回非零值: 管理员权限
        - 返回 0: 普通用户权限

    异常处理:
        - 在非 Windows 系统上会抛出异常
        - 捕获异常并返回 False
    """
    try:
        # 延迟导入 ctypes（Windows API 调用库）
        import ctypes

        # 调用 Windows API 检查管理员权限
        # windll: 访问 Windows DLL（32位和64位兼容）
        # shell32: Shell32.dll，包含 Shell 相关函数
        # IsUserAnAdmin(): 检查当前用户是否为管理员
        return ctypes.windll.shell32.IsUserAnAdmin() != 0

    except Exception:
        # 非 Windows 系统或 API 调用失败
        return False


# ========== 主程序入口 ==========
# 当直接运行此脚本时（而非作为模块导入），执行以下代码
if __name__ == "__main__":
    try:
        # 打印程序标题
        print("Arknights Token Capture Proxy", flush=True)
        print("=" * 40, flush=True)

        # 检查管理员权限
        if not is_admin():
            print("[Error] Need admin privileges", flush=True)
            exit(1)  # 退出程序，返回错误码 1

        print("[OK] Admin confirmed", flush=True)

        # 定义进度回调函数
        # 将进度转换为百分比显示
        def progress(msg, prog):
            print(f"[{prog*100:.0f}%] {msg}", flush=True)

        # 启动 token 捕获
        # timeout=120: 等待 120 秒
        token = capture_token(timeout=120, progress_callback=progress)

        # 输出结果
        if token:
            print(f"\n[OK] Token captured, length: {len(token)}", flush=True)
        else:
            print("\n[Failed] Capture failed", flush=True)

    except Exception as e:
        # 捕获所有未预期的异常
        print(f"\n[Exception] {type(e).__name__}: {e}", flush=True)

        # 导入 traceback 模块，打印详细的堆栈信息
        import traceback
        traceback.print_exc()

        # 退出程序，返回错误码 1
        exit(1)
