"""Helpers for iKuai integration."""
from __future__ import annotations

import re
from urllib.parse import unquote

def extract_name_from_label(label: str | None) -> str:
    """从 iKuai 的备注标签中提取名称. 例如: 192.168.1.2(我的手机) -> 我的手机."""
    if not label or label == "":
        return ""
    
    try:
        # 1. 强制转为字符串并进行 URL 解码
        decoded_label = unquote(str(label))
        
        # 2. 健壮性检查：如果解码后还包含 %，说明可能存在双重编码，再解一次
        if "%" in decoded_label:
            decoded_label = unquote(decoded_label)
            
        # 3. 尝试提取括号内的内容
        match = re.search(r'\((.+?)\)', decoded_label)
        if match:
            return match.group(1).strip()
        
        # 4. 如果没有括号，直接返回解码后的文字
        return decoded_label.strip()
    except Exception:
        # 万一出错，至少返回原始字符串的字符串形式，保证不崩
        return str(label)

def format_mac(mac: str) -> str:
    """标准化 MAC 地址格式."""
    return mac.replace("-", ":").lower()