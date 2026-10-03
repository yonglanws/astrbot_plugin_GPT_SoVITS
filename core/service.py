from typing import Any

from astrbot.api import logger

from .client import GSVApiClient, GSVRequestResult
from .config import PluginConfig
from .local_data import LocalDataManager


class GPTSoVITSService:
    def __init__(
        self,
        config: PluginConfig,
        client: GSVApiClient,
        local_data: LocalDataManager,
    ):
        self.cfg = config.model
        self.default_params = config.default_params
        self.client = client
        self.local_data = local_data
        self._loaded_gpt: str | None = None
        self._loaded_sovits: str | None = None

    async def load_model(self):
        if self.cfg.gpt_path:
            result = await self.client.set_gpt_weights(self.cfg.gpt_path)
            if result.ok:
                logger.info(f"GPT 模型已加载: {self.cfg.gpt_path}")
                self._loaded_gpt = self.cfg.gpt_path
            else:
                logger.error(f"GPT 模型加载失败: {result.error}")

        if self.cfg.sovits_path:
            result = await self.client.set_sovits_weights(self.cfg.sovits_path)
            if result.ok:
                logger.info(f"SoVITS 模型已加载: {self.cfg.sovits_path}")
                self._loaded_sovits = self.cfg.sovits_path
            else:
                logger.error(f"SoVITS 模型加载失败: {result.error}")

    async def _ensure_model_loaded(self, gpt_path: str | None, sovits_path: str | None):
        if gpt_path and gpt_path != self._loaded_gpt:
            result = await self.client.set_gpt_weights(gpt_path)
            if result.ok:
                logger.info(f"动态切换 GPT 模型: {gpt_path}")
                self._loaded_gpt = gpt_path
            else:
                logger.error(f"GPT 模型切换失败: {result.error}")

        if sovits_path and sovits_path != self._loaded_sovits:
            result = await self.client.set_sovits_weights(sovits_path)
            if result.ok:
                logger.info(f"动态切换 SoVITS 模型: {sovits_path}")
                self._loaded_sovits = sovits_path
            else:
                logger.error(f"SoVITS 模型切换失败: {result.error}")

    async def inference(
        self,
        text: str,
        extra_params: dict[str, Any] | None = None,
    ) -> GSVRequestResult:
        params = self.default_params.copy()
        if text:
            params["text"] = text

        if extra_params:
            for k, v in extra_params.items():
                if v is not None:
                    params[k] = v
            logger.debug(f"合并后 TTS 参数: text_lang={params.get('text_lang')}, "
                         f"ref_audio_path={params.get('ref_audio_path')}")

        gpt_path = params.pop("gpt_path", None)
        sovits_path = params.pop("sovits_path", None)
        await self._ensure_model_loaded(gpt_path, sovits_path)

        cached_audio = self.local_data.get_cached_audio(params)
        if cached_audio:
            cache_path, cached_data = cached_audio
            logger.info(f"命中语音缓存: {cache_path}")
            return GSVRequestResult(
                ok=True,
                data=cached_data,
                text=str(params.get("text", "")),
                file_path=str(cache_path),
            )

        logger.info(f"向 GSV 发起 TTS 请求，文本: {text!r}, text_lang={params.get('text_lang')}")
        result = await self.client.tts(params)

        if bool(result):
            cache_path = self.local_data.save_audio(result.data, params)
            if cache_path:
                result.file_path = str(cache_path)
        else:
            logger.error(f"TTS 推理失败: {result.error}")

        return result

    async def restart(self):
        result = await self.client.restart()
        if not result.ok:
            logger.error(f"重启失败: {result.error}")
