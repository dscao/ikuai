"""Helpers for iKuai integration."""
from __future__ import annotations

import re
from urllib.parse import unquote

def extract_name_from_label(label: str) -> str:
    """从 iKuai 的备注标签中提取名称. 例如: 192.168.1.2(我的手机) -> 我的手机."""
    if not label:
        return ""
    label = unquote(label)
    match = re.search(r'\((.+?)\)', label)
    if match:
        return match.group(1).strip()
    return label.strip()

def format_mac(mac: str) -> str:
    """标准化 MAC 地址格式."""
    return mac.replace("-", ":").lower()