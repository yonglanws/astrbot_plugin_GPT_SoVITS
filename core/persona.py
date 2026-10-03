from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .config import ConfigNode, PluginConfig


class PersonaEntry(ConfigNode):
    persona_id: str = ""
    gpt_path: str = ""
    sovits_path: str = ""
    ref_audio_path: str = ""
    prompt_text: str = ""
    prompt_lang: str = ""
    text_lang: str = ""
    speed_factor: float = 1.0
    fragment_interval: float = 0.3

    def __init__(self, data: dict[str, Any]):
        super().__init__(data)
        self.gpt_path = PluginConfig.normalize_path(self.gpt_path)
        self.sovits_path = PluginConfig.normalize_path(self.sovits_path)
        self.ref_audio_path = PluginConfig.normalize_path(self.ref_audio_path)

    def to_params(self) -> dict[str, Any]:
        params = {}
        if self.gpt_path:
            params["gpt_path"] = self.gpt_path
        if self.sovits_path:
            params["sovits_path"] = self.sovits_path
        if self.ref_audio_path:
            params["ref_audio_path"] = self.ref_audio_path
        if self.prompt_text:
            params["prompt_text"] = self.prompt_text
        if self.prompt_lang:
            params["prompt_lang"] = self.prompt_lang
        if self.text_lang:
            params["text_lang"] = self.text_lang
        if self.speed_factor != 1.0:
            params["speed_factor"] = self.speed_factor
        if self.fragment_interval != 0.3:
            params["fragment_interval"] = self.fragment_interval
        return params


class PersonaManager:
    def __init__(self, config: PluginConfig):
        self.cfg = config
        self.entries: dict[str, PersonaEntry] = {}
        for item in self.cfg.persona_storage:
            pid = item.get("persona_id", "").strip()
            if pid:
                self.entries[pid] = PersonaEntry(item)
        logger.info(f"已注册人物: {list(self.entries.keys())}")

    def get_entry(self, persona_id: str) -> PersonaEntry | None:
        return self.entries.get(persona_id)

    async def get_current_persona_id(self, event: AstrMessageEvent) -> str | None:
        try:
            conv_mgr = self.cfg.context.conversation_manager
            uid = event.unified_msg_origin
            curr_cid = await conv_mgr.get_curr_conversation_id(uid)
            if not curr_cid:
                logger.info("当前无活跃对话，无法获取人格ID")
                return None

            conversation = await conv_mgr.get_conversation(
                uid, curr_cid, create_if_not_exists=False
            )
            if not conversation:
                logger.info(f"对话 {curr_cid} 不存在，无法获取人格ID")
                return None

            persona_id = getattr(conversation, "persona_id", None)
            if not persona_id:
                logger.info("当前对话未绑定人格ID")
                return None

            logger.info(f"当前人格ID: {persona_id}")
            return persona_id

        except Exception as e:
            logger.warning(f"获取当前人格ID失败: {e}")
        return None

    async def fetch_and_cache_persona_id(self, event: AstrMessageEvent) -> str | None:
        """在 LLM 请求开始时获取人格ID并缓存到 event"""
        persona_id = await self.get_current_persona_id(event)
        if persona_id:
            event.set_extra("gsv_persona_id", persona_id)
        return persona_id

    def get_cached_persona_id(self, event: AstrMessageEvent) -> str | None:
        return event.get_extra("gsv_persona_id")

    async def get_params_for_event(self, event: AstrMessageEvent) -> dict[str, Any] | None:
        persona_id = event.get_extra("gsv_persona_id")
        if not persona_id:
            persona_id = await self.get_current_persona_id(event)

        if not persona_id:
            return None

        entry = self.get_entry(persona_id)
        if entry:
            logger.info(f"使用人物配置: {persona_id}")
            return entry.to_params()

        logger.info(f"人格ID {persona_id} 无对应人物配置，取消语音合成")
        return None
