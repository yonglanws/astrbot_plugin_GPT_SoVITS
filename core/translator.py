from __future__ import annotations

from astrbot.api import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .config import PluginConfig

_TRANSLATION_SYSTEM_PROMPT = (
    "你是一个专业的中日翻译专家。请将用户给出的中文文本翻译成自然流畅的日语。"
    "要求：\n"
    "1. 仅输出翻译结果，不要包含任何解释、注释或多余内容\n"
    "2. 翻译应准确传达原文含义，语气自然\n"
    "3. 当翻译“我”时，应使用“ぼく”\n"
    "4. 使用常见的日语表达方式，避免生硬的直译\n"
    "5. 保持原文的情感色彩和语气\n"
    "6. 若原文包含emoji或颜文字，请一并删除，仅保留文字\n"
    "7. 若原文包含换行符和多余空格，请将其删除，保持文本连贯\n"
    "8. 若原文包含英文或其他语言，请将其翻译成假名或日语形式，不要保留其他语言\n"
    "9. 下面的内容是角色的全名，若原文包含角色名字，你可以参考下面的内容进行翻译，如果角色的名字只有一半，你只需要翻译一半\n"
    "初音未来 (はつね ミク) 镜音铃 (かがみね リン) 镜音连 (かがみね レン) 巡音流歌 (めぐりね ルカ) MEIKO (メイコ) KAITO (カイト) 星乃一歌 (ほしの いちか) 天马咲希 (てんま さき) 望月穗波 (もちづき ほなみ) 日野森志步 (ひのもり しほ) 花里实乃里 (はなさと みのり) 桐谷遥 (きりたに はるか) 桃井爱莉 (ももい あいり) 日野森雫 (ひのもり しずく) 小豆泽心羽 (あずさわ こはね) 白石杏 (しらいし あん) 东云彰人 (しののめ あきと) 青柳冬弥 (あおやぎ とうや) 天马司 (てんま つかさ) 凤笑梦 (おおとり えむ) 草薙宁宁 (くさなぎ ねね) 神代类 (かみしろ るい) 宵崎奏 (よいさき かなで) 朝比奈真冬 (あさひな まふゆ) 东云绘名 (しののめ えな) 晓山瑞希 (あきやま みずき)"
)

_TRANSLATION_SYSTEM_PROMPT_EN = (
    "你是一个专业的翻译专家。请将用户给出的文本翻译成自然流畅的英语。"
    "要求：\n"
    "1. 仅输出翻译结果，不要包含任何解释、注释或多余内容\n"
    "2. 翻译应准确传达原文含义，语气自然\n"
    "3. 使用常见的英语表达方式，避免生硬的直译\n"
    "4. 保持原文的情感色彩和语气\n"
    "5. 若原文包含emoji或颜文字，请一并删除，仅保留文字\n"
    "6. 若原文包含换行符和多余空格，请将其删除，保持文本连贯\n"
    "7. 人名等专有名词使用罗马音或通用英文写法\n"
)


class Translator:
    def __init__(self, config: PluginConfig):
        self.cfg = config

    async def translate(
        self,
        event: AstrMessageEvent,
        text: str,
        force: bool = False,
        target_lang: str = "ja",
    ) -> str | None:
        if not force and not self.cfg.translate.enabled:
            return None

        if not text or not text.strip():
            return None

        system_prompt = (
            _TRANSLATION_SYSTEM_PROMPT
            if target_lang != "en"
            else _TRANSLATION_SYSTEM_PROMPT_EN
        )

        try:
            provider = self.cfg.get_translate_provider(event.unified_msg_origin)
            resp = await provider.text_chat(
                prompt=text,
                system_prompt=system_prompt,
            )
            translated = resp.completion_text.strip()
            if not translated:
                logger.warning("翻译结果为空，将使用原文进行语音合成")
                return None

            logger.info(f"翻译完成: {text!r} -> {translated!r}")
            return translated

        except Exception as e:
            logger.error(f"翻译失败，将使用原文进行语音合成: {e}")
            return None

    def get_tts_override_params(self) -> dict:
        params = {}
        target_lang = self.cfg.translate.target_lang
        if target_lang:
            params["text_lang"] = target_lang
        return params
