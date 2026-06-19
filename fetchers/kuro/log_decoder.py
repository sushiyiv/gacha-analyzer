# -*- coding: utf-8 -*-
"""鸣潮游戏日志解密 - 纯Python实现，无需WaveToolsHelper"""

import re
from typing import List, Optional

# 编码表：每个高位字节(0x80-0xFF)映射到1或2个字符
# 0x80-0x9F 和 0xC0-0xDF 各映射2个字符，通过 bit0 消歧
# 0xA0-0xBF 和 0xE0-0xFF 各映射1个字符（大写字母/符号）
_BYTE_TO_CHARS = {
    0x80: ('%', 'o'), 0x81: ('$', 'n'), 0x82: ("'", 'm'), 0x83: ('&', 'l'),
    0x84: ('!', 'k'), 0x85: (' ', 'j'), 0x86: ('#', 'i'), 0x87: ('"', 'h'),
    0x88: ('-', 'g'), 0x89: (',', 'f'), 0x8a: ('/', 'e'), 0x8b: ('.', 'd'),
    0x8c: (')', 'c'), 0x8d: ('(', 'b'), 0x8e: ('+', 'a'), 0x8f: ('*', '`'),
    0x90: ('5',),
    0x91: ('4', '~'), 0x92: ('7', '}'), 0x93: ('6', '|'), 0x94: ('1', '{'),
    0x95: ('0', 'z'), 0x96: ('3', 'y'), 0x97: ('2', 'x'), 0x98: ('=', 'w'),
    0x99: ('<', 'v'), 0x9a: ('?', 'u'), 0x9b: ('>', 't'), 0x9c: ('9', 's'),
    0x9d: ('8', 'r'), 0x9e: (';', 'q'), 0x9f: (':', 'p'),
    0xa0: 'O', 0xa1: 'N', 0xa2: 'M', 0xa3: 'L', 0xa4: 'K', 0xa5: 'J',
    0xa6: 'I', 0xa7: 'H', 0xa8: 'G', 0xa9: 'F', 0xaa: 'E', 0xab: 'D',
    0xac: 'C', 0xad: 'B', 0xae: 'A', 0xaf: '@',
    0xb0: '_', 0xb1: '^', 0xb2: ']', 0xb3: '\\', 0xb4: '[', 0xb5: 'Z',
    0xb6: 'Y', 0xb7: 'X', 0xb8: 'W', 0xb9: 'V', 0xba: 'U', 0xbb: 'T',
    0xbc: 'S', 0xbd: 'R', 0xbe: 'Q', 0xbf: 'P',
    0xc0: ('/', 'e'), 0xc1: ('.', 'd'), 0xc2: ('-', 'g'), 0xc3: (',', 'f'),
    0xc4: ('+', 'a'), 0xc5: ('*', '`'), 0xc6: (')', 'c'), 0xc7: ('(', 'b'),
    0xc8: ("'", 'm'), 0xc9: ('&', 'l'), 0xca: ('%', 'o'), 0xcb: ('$', 'n'),
    0xcc: ('#', 'i'), 0xcd: ('"', 'h'), 0xce: ('!', 'k'), 0xcf: (' ', 'j'),
    0xd0: ('?', 'u'), 0xd1: ('>', 't'), 0xd2: ('=', 'w'), 0xd3: ('<', 'v'),
    0xd4: (';', 'q'), 0xd5: (':', 'p'), 0xd6: ('9', 's'), 0xd7: ('8', 'r'),
    0xd8: ('7', '}'), 0xd9: ('6', '|'), 0xda: ('5',), 0xdb: ('4', '~'),
    0xdc: ('3', 'y'), 0xdd: ('2', 'x'), 0xde: ('1', '{'), 0xdf: ('0', 'z'),
    0xe0: 'E', 0xe1: 'D', 0xe2: 'G', 0xe3: 'F', 0xe4: 'A', 0xe5: '@',
    0xe6: 'C', 0xe7: 'B', 0xe8: 'M', 0xe9: 'L', 0xea: 'O', 0xeb: 'N',
    0xec: 'I', 0xed: 'H', 0xee: 'K', 0xef: 'J', 0xf0: 'U', 0xf1: 'T',
    0xf2: 'W', 0xf3: 'V', 0xf4: 'Q', 0xf5: 'P', 0xf6: 'S', 0xf7: 'R',
    0xf8: ']', 0xf9: '\\', 0xfa: '_', 0xfb: '^', 0xfc: 'Y', 0xfd: 'X',
    0xfe: '[', 0xff: 'Z',
}

# URL中有效的字符集（RFC 3986）
_URL_VALID_CHARS = set(
    'abcdefghijklmnopqrstuvwxyz'
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    '0123456789'
    '-_.~:/?#[]@!$&\'()*+,;='
)


def _decode_byte(b):
    """解码单个字节为字符"""
    if b < 0x80:
        return chr(b)
    entry = _BYTE_TO_CHARS.get(b)
    if entry is None:
        return None
    if isinstance(entry, str):
        return entry
    if b < 0xC0:
        idx = 0 if (b & 1) else 1
    else:
        idx = 1 if (b & 1) else 0
    return entry[idx]


def _is_encoded_char(b, ch):
    """检查字节b是否能解码为字符ch"""
    if b < 0x80:
        return chr(b) == ch
    entry = _BYTE_TO_CHARS.get(b)
    if entry is None:
        return False
    if isinstance(entry, str):
        return entry == ch
    return ch in entry


def _match_encoded_literal(data, offset, text):
    """检查data[offset:]是否以text的编码形式开头"""
    for i, ch in enumerate(text):
        if offset + i >= len(data):
            return False
        if not _is_encoded_char(data[offset + i], ch):
            return False
    return True


def _decode_url_at(data, start):
    """从start位置开始解码一个URL，自动判断URL结束位置"""
    url_chars = []
    j = start
    max_len = 1024

    while j < len(data) and j - start < max_len:
        b = data[j]
        if b < 0x80:
            # 普通ASCII字符
            ch = chr(b)
            if ch in _URL_VALID_CHARS:
                url_chars.append(ch)
                j += 1
            else:
                # 非URL字符，URL结束
                break
        else:
            ch = _decode_byte(b)
            if ch is None:
                break
            if ch not in _URL_VALID_CHARS:
                break
            url_chars.append(ch)
            j += 1

    return ''.join(url_chars)


def find_gacha_urls(data):
    """从游戏日志数据中查找所有加密的抽卡URL"""
    urls = []
    prefix = "https://aki-gm-resources.aki-game.com/aki/gacha/index.html"
    prefix_len = len(prefix)

    i = 0
    while i < len(data) - prefix_len:
        if data[i] < 0x80:
            i += 1
            continue

        if _match_encoded_literal(data, i, prefix):
            url = _decode_url_at(data, i)
            if 'aki-game' in url and 'gacha' in url and 'record' in url:
                urls.append(url)
            i += len(url)
        else:
            i += 1

    return urls


def extract_gacha_urls_from_log(log_path):
    """从游戏日志文件中提取抽卡URL"""
    try:
        with open(log_path, 'rb') as f:
            data = f.read()
    except (OSError, IOError):
        return []
    return find_gacha_urls(data)


def extract_gacha_url_from_cache(cache_path):
    """从浏览器缓存文件中提取抽卡URL（明文格式）"""
    try:
        with open(cache_path, 'rb') as f:
            data = f.read()
        content = data.decode('utf-8', errors='ignore')
        matches = re.findall(
            r'"url":"(https://aki-gm-resources\.aki-game\.com/aki/gacha/index\.html#/record\?[^"]+)"',
            content
        )
        if matches:
            return matches[-1].replace("\\u0026", "&")
    except (OSError, IOError):
        pass
    return None