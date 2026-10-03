import base64
import json
import random
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Record
from astrbot.core.platform import AstrMessageEvent

from .core.client import GSVApiClient, GSVRequestResult
from .core.config import PluginConfig
from .core.local_data import LocalDataManager
from .core.persona import PersonaManager
from .core.say_parser import detect_text_lang, parse_say_command
from .core.service import GPTSoVITSService
from .core.translator import Translator


class GPTSoVITSPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.local_data = LocalDataManager(self.cfg)
        self.persona_mgr = PersonaManager(self.cfg)
        self.client = GSVApiClient(self.cfg)
        self.translator = Translator(self.cfg)
        self.service = GPTSoVITSService(self.cfg, self.client, self.local_data)

    async def initialize(self):
        self.local_data.cleanup_legacy_dir()
        self.local_data.cleanup_expired()
        if self.cfg.enabled:
            await self.service.load_model()
            logger.info("GPT-SoVITS 插件已初始化")

    async def terminate(self):
        await self.client.close()

    @staticmethod
    def _to_record(res: GSVRequestResult) -> Record:
        if res.file_path:
            try:
                return Record.fromFileSystem(res.file_path)
            except Exception:
                logger.warning(f"无法读取文件：{res.file_path}, 已忽略")

        if not res.data:
            raise ValueError("无法获取结果数据")

        b64 = base64.urlsafe_b64encode(res.data).decode()
        return Record.fromBase64(b64)

    async def _get_persona_lookup(self) -> tuple[set[str], dict[str, str]]:
        """
        收集 `说` 命令可用人格识别词。

        返回 (识别词集合, 别名映射)：
        - 识别词集合 = 已注册人格名(persona_id) ∪ characters.json 中的别名
        - 别名映射: 别名/缩写/全名 -> 已注册的 persona_id
        """
        registered = set(self.persona_mgr.entries.keys())
        try:
            mgr = getattr(self.context, "persona_manager", None)
            if mgr is not None:
                for p in await mgr.get_all_personas():
                    pid = (getattr(p, "persona_id", "") or "").strip()
                    if pid:
                        registered.add(pid)
        except Exception as e:
            logger.warning(f"获取人格列表失败: {e}")

        alias_map: dict[str, str] = {}
        for ch in self._load_characters():
            candidates = [
                str(ch.get("fullNameChinese") or "").strip(),
                str(ch.get("fullName") or "").strip(),
                str(ch.get("name") or "").strip(),
                *[str(a).strip() for a in ch.get("aliases") or []],
            ]
            # 角色对应的已注册人格：优先中文名，其次日文名，其次缩写
            target = next((c for c in candidates[:3] if c in registered), None)
            if not target:
                continue
            for word in candidates:
                if word and word not in registered:
                    alias_map.setdefault(word, target)

        return registered | set(alias_map.keys()), alias_map

    @staticmethod
    def _load_characters() -> list[dict]:
        """读取插件目录下的 characters.json（角色别名表），每次调用重读以支持热更新"""
        path = Path(__file__).resolve().parent / "characters.json"
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"读取 characters.json 失败: {e}")
        return []

    async def _translate_and_synthesize(
        self,
        event: AstrMessageEvent,
        text: str,
        extra_params: dict | None = None,
        persona_params_override: dict | None = None,
        forced_lang: str | None = None,
        detect_first: bool = False,
    ) -> GSVRequestResult | None:
        if persona_params_override is not None:
            persona_params = persona_params_override
        else:
            persona_params = await self.persona_mgr.get_params_for_event(event)
            if persona_params is None:
                logger.info("人格不匹配，取消语音合成")
                return None

        translate_override = {}
        lang_override = {}

        if forced_lang in ("ja", "en"):
            # 显式指定日/英：强制 LLM 翻译后合成
            translated = await self.translator.translate(
                event, text, force=True, target_lang=forced_lang
            )
            if not translated:
                logger.warning(f"指定 {forced_lang} 但翻译失败，取消语音合成")
                return None
            text = translated
            lang_override["text_lang"] = forced_lang
        elif forced_lang == "zh":
            # 显式指定中文：不翻译
            lang_override["text_lang"] = "zh"
        else:
            detected = detect_text_lang(text) if self.cfg.auto_detect_lang else None

            if detect_first and detected:
                # `说` 命令：输入语言即发音语言，跳过全局翻译
                logger.info(f"自动识别语言: {detected}，以输入语言直接合成")
                lang_override["text_lang"] = detected
            elif self.cfg.translate.enabled:
                # 全局自动翻译（主要服务概率自动转语音流程）
                try:
                    logger.info(f"翻译已启用，开始翻译文本: {text!r}")
                    translated = await self.translator.translate(event, text)
                    if translated:
                        text = translated
                        translate_override = self.translator.get_tts_override_params()
                        logger.info(f"翻译成功，TTS 覆盖参数: {translate_override}")
                    else:
                        logger.warning("翻译失败，取消语音合成")
                        return None
                except Exception as e:
                    logger.error(f"翻译过程异常: {e}")
                    return None
            elif detected:
                # 翻译关闭时按检测语言发音
                lang_override["text_lang"] = detected

        # 用户显式指定的语言优先级最高，其次人格配置，再次全局翻译配置
        if extra_params:
            merged = {
                **extra_params,
                **translate_override,
                **persona_params,
                **lang_override,
            }
        else:
            merged = {**translate_override, **persona_params, **lang_override}

        try:
            res = await self.service.inference(text, extra_params=merged)
            if not bool(res):
                logger.warning(f"语音合成失败: {res.error}")
                return None
            return res
        except Exception as e:
            logger.error(f"语音合成异常: {e}")
            return None

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req):
        """LLM 请求开始时获取并缓存人格ID，确保整个对话流程使用同一人格"""
        try:
            await self.persona_mgr.fetch_and_cache_persona_id(event)
        except Exception as e:
            logger.error(f"on_llm_request 获取人格ID异常: {e}")

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """LLM 响应后自动转语音：在 LLM 返回结果时触发"""
        try:
            await self._handle_auto_tts_from_llm(event, resp)
        except Exception as e:
            logger.error(f"on_llm_response 自动转语音异常: {e}")

    async def _handle_auto_tts_from_llm(
        self, event: AstrMessageEvent, resp: LLMResponse
    ):
        if not self.cfg.enabled:
            return

        cfg = self.cfg.auto

        if random.random() > cfg.tts_prob:
            return

        text = resp.completion_text
        if not text or not text.strip():
            return

        if len(text) > cfg.max_msg_len:
            return

        logger.info(f"自动转语音触发(LLM响应)，文本: {text!r}")

        res = await self._translate_and_synthesize(
            event, text
        )
        if res is None:
            logger.warning("自动转语音: 合成失败，保留原文")
            return

        try:
            record = self._to_record(res)
            await event.send(event.chain_result([record]))
            logger.info("自动转语音: 语音已发送")
        except Exception as e:
            logger.error(f"自动转语音发送失败: {e}")

    @filter.command("说", alias={"gsv", "GSV"})
    async def on_command(self, event: AstrMessageEvent):
        """说 <内容> [人格] [语言]，人格与语言顺序不限；语言支持：中文/日文/英文 及其简写"""
        if not self.cfg.enabled:
            return

        raw = event.message_str.partition(" ")[2].strip()
        lookup_words, alias_map = await self._get_persona_lookup()
        parsed = parse_say_command(raw, lookup_words)
        persona_id = alias_map.get(parsed.persona_id, parsed.persona_id)

        if not parsed.text:
            yield event.plain_result("请输入要合成的文本内容")
            return

        if persona_id:
            entry = self.persona_mgr.get_entry(persona_id)
            if entry is None:
                yield event.plain_result(
                    f"人格 {persona_id} 未配置语音参数，"
                    f"请在插件配置的 persona_storage 中为其添加条目"
                )
                return
        else:
            cur_id = await self.persona_mgr.get_current_persona_id(event)
            entry = self.persona_mgr.get_entry(cur_id) if cur_id else None
            if entry is None:
                yield event.plain_result("当前人格无语音模型文件，无法合成语音")
                return

        logger.info(
            f"手动合成语音，文本: {parsed.text!r}, "
            f"人格: {persona_id or '(当前)'}, 语言: {parsed.lang or '(自动)'}"
        )
        res = await self._translate_and_synthesize(
            event,
            parsed.text,
            persona_params_override=entry.to_params(),
            forced_lang=parsed.lang,
            detect_first=True,
        )

        if res is None:
            yield event.plain_result("语音合成失败")
            return

        yield event.chain_result([self._to_record(res)])

    @filter.command("重启GSV", alias={"重启gsv"})
    async def tts_control(self, event: AstrMessageEvent):
        """重启GPT_SoVITS"""
        if not self.cfg.enabled:
            return
        yield event.plain_result("重启TTS中...(报错信息请忽略，等待一会即可完成重启)")
        await self.service.restart()

    @filter.llm_tool()
    async def gsv_tts(self, event: AstrMessageEvent, message: str = ""):
        """用语音输出要讲的话

        Args:
            message(string): 要讲的话
        """
        try:
            res = await self._translate_and_synthesize(event, message)
            if res is None:
                return "语音合成失败"
            seg = self._to_record(res)
            await event.send(event.chain_result([seg]))
        except Exception as e:
            logger.error(f"gsv_tts 工具调用失败: {e}")
            return str(e)
