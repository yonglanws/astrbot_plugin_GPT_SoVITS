from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.star import Context
from astrbot.core.provider.provider import Provider
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


class ConfigNode:
    def __init__(self, data: dict[str, Any]):
        for key, value in data.items():
            if hasattr(self, key) or key in self.__annotations__:
                setattr(self, key, value)


class AutoConfig(ConfigNode):
    only_llm_result: bool = True
    tts_prob: float = 0.15
    max_msg_len: int = 50


class ClientConfig(ConfigNode):
    base_url: str = "http://127.0.0.1:9880"
    timeout: int = 60


class ModelConfig(ConfigNode):
    gpt_path: str = ""
    sovits_path: str = ""


class TranslateConfig(ConfigNode):
    enabled: bool = False
    provider_id: str = ""
    target_lang: str = "ja"


class CacheConfig(ConfigNode):
    enabled: bool = True
    expire_hours: int = 0
    path: str = ""


class PluginConfig:
    # 旧版本的默认缓存目录（持久化），仅用于迁移清理
    LEGACY_CACHE_PATH = "data/plugins_data/astrbot_plugin_GPT_SoVITS/audio"
    enabled: bool
    auto: AutoConfig
    client: ClientConfig
    model: ModelConfig
    default_params: dict[str, Any]
    translate: TranslateConfig
    cache: CacheConfig
    persona_storage: list[dict[str, Any]]
    auto_detect_lang: bool

    def __init__(self, config: dict[str, Any], context: Context):
        self.context = context
        self._raw_config = config

        self.enabled = config.get("enabled", False)
        self.auto = AutoConfig(config.get("auto", {}))
        self.client = ClientConfig(config.get("client", {}))
        self.model = ModelConfig(config.get("model", {}))
        self.default_params = config.get("default_params", {})
        self.translate = TranslateConfig(config.get("translate", {}))
        self.cache = CacheConfig(config.get("cache", {}))
        self.persona_storage = config.get("persona_storage", [])
        self.auto_detect_lang = config.get("auto_detect_lang", True)

        self.audio_dir = self._resolve_audio_dir()

        self.model.gpt_path = self.normalize_path(self.model.gpt_path)
        self.model.sovits_path = self.normalize_path(self.model.sovits_path)
        self.default_params["ref_audio_path"] = self.normalize_path(
            self.default_params.get("ref_audio_path", "")
        )
        self.cache.path = self.normalize_path(self.cache.path)

    def _resolve_audio_dir(self) -> Path:
        raw_path = (self.cache.path or "").strip().replace("\\", "/")
        if not raw_path or raw_path == self.LEGACY_CACHE_PATH:
            # 默认使用 AstrBot 临时目录，缓存文件由 AstrBot 自动清理
            path = Path(get_astrbot_temp_path()) / "astrbot_plugin_GPT_SoVITS"
        else:
            path = Path(raw_path)
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    @staticmethod
    def normalize_path(path: str) -> str:
        return path.replace("\\", "/")

    def save_config(self):
        try:
            self.context.config.save_config()
            logger.info("配置已保存")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def get_translate_provider(self, umo: str | None = None) -> Provider:
        provider = self.context.get_provider_by_id(
            self.translate.provider_id
        ) or self.context.get_using_provider(umo)

        if not isinstance(provider, Provider):
            raise RuntimeError("未找到可用的翻译 LLM Provider")

        return provider
