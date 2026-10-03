from __future__ import annotations

from dataclasses import dataclass

# 语言 token -> text_lang
LANG_TOKENS: dict[str, str] = {
    "中文": "zh",
    "中": "zh",
    "日文": "ja",
    "日": "ja",
    "英文": "en",
    "英语": "en",
    "英": "en",
}

# 人格名最多允许的 token 数（防止超长拼接误匹配）
MAX_PERSONA_TOKENS = 4


def detect_text_lang(text: str) -> str | None:
    """
    轻量语言检测（zh/ja/en），用于未显式指定语言时自动设置 text_lang：
    - 含日文假名（平假名/片假名）-> ja（中文文本不会出现假名）
    - 含 CJK 汉字 -> zh
    - 含拉丁字母 -> en
    - 无法判断（纯数字/符号）-> None
    """
    if not text:
        return None
    if any("\u3040" <= c <= "\u30ff" for c in text):
        return "ja"
    if any("\u4e00" <= c <= "\u9fff" for c in text):
        return "zh"
    if any(c.isascii() and c.isalpha() for c in text):
        return "en"
    return None


@dataclass
class ParsedSayCommand:
    text: str
    persona_id: str | None
    lang: str | None


def parse_say_command(raw: str, persona_ids: list[str] | set[str]) -> ParsedSayCommand:
    """
    解析 `说` 命令参数：正文 + 可选人格名 + 可选语言。

    - 人格名可位于正文之前或之后（`说 镜华 你好` / `说 你好 镜华` 均可）；
    - 语言词从消息末尾剥离，支持与人格名任意组合顺序（`说 你好 镜华 日` / `说 你好 日 镜华`）；
    - 人格名支持含空格的多 token 名（最长优先匹配）；
    - 分割点为空格，剩余部分（含空格）整体作为正文，不在空格处截断；
    - 剥离后正文为空时，放弃剥离结果，把原始文本整体当作正文。
    """
    tokens = raw.split()
    if not tokens:
        return ParsedSayCommand("", None, None)

    known_ids = {p.strip() for p in persona_ids if p and p.strip()}
    lang: str | None = None
    persona_id: str | None = None

    # 尾部剥离：语言词与人格名，顺序不限
    changed = True
    while tokens and changed:
        changed = False

        tail = tokens[-1]
        if lang is None and tail in LANG_TOKENS:
            lang = LANG_TOKENS[tail]
            tokens.pop()
            changed = True
            continue

        if persona_id is None:
            matched = _match_persona_tail(tokens, known_ids)
            if matched:
                n, name = matched
                persona_id = name
                del tokens[-n:]
                changed = True

    # 头部剥离：仅人格名（语言词是通用词，前置易误伤正文，仍只从尾部识别）
    changed = True
    while tokens and changed and persona_id is None:
        changed = False
        matched = _match_persona_head(tokens, known_ids)
        if matched:
            n, name = matched
            persona_id = name
            del tokens[:n]
            changed = True

    text = " ".join(tokens)
    if not text:
        # 没有正文剩余：参数失去意义，回退为纯文本朗读
        return ParsedSayCommand(" ".join(raw.split()), None, None)
    return ParsedSayCommand(text, persona_id, lang)


def _match_persona_tail(
    tokens: list[str], persona_ids: set[str]
) -> tuple[int, str] | None:
    """尝试用尾部连续 token 拼接人格名，最长优先匹配"""
    max_n = min(len(tokens), MAX_PERSONA_TOKENS)
    for n in range(max_n, 0, -1):
        cand = " ".join(tokens[-n:])
        if cand in persona_ids:
            return n, cand
    return None


def _match_persona_head(
    tokens: list[str], persona_ids: set[str]
) -> tuple[int, str] | None:
    """尝试用头部连续 token 拼接人格名，最长优先匹配"""
    max_n = min(len(tokens), MAX_PERSONA_TOKENS)
    for n in range(max_n, 0, -1):
        cand = " ".join(tokens[:n])
        if cand in persona_ids:
            return n, cand
    return None
