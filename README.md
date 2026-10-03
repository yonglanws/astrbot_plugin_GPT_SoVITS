<div align="center">

# astrbot_plugin_GPT_SoVITS

_为 AstrBot 提供多角色、多语言的 GPT-SoVITS 语音合成（TTS）_

[![License](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0.html)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-4.0%2B-orange.svg)](https://github.com/AstrBotDevs/AstrBot)

</div>

---

本插件基于QQ BOT mzkbot设计，为mzkbot核心模块之一

本插件基于 [Zhalslar/astrbot_plugin_GPT_SoVITS](https://github.com/Zhalslar/astrbot_plugin_GPT_SoVITS) 二次开发重构，底层调用 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) v2 API，把 AstrBot 的文本输出变成语音。

在原版基础上重写了架构，并新增：

- **多人格音色**：每个 AstrBot 人格绑定独立的 GPT/SoVITS 模型与参考音频，切换人格即切换音色，模型按需动态加载
- **`说` 命令参数化**：可在命令中直接指定人格与语言，人格名前置后置均可，支持角色别名
- **角色别名识别**：通过 `characters.json` 映射角色的中文名、日文名、罗马音缩写与昵称
- **多语言合成**：中文 / 日文 / 英文，可显式指定（LLM 翻译）或自动识别
- **自动转语音**：LLM 回复按概率自动变语音，LLM 工具调用由模型自主决定
- **参数级缓存**：相同参数直接复用音频，默认存放在 AstrBot 临时目录，自动清理

## 目录

- [1. 功能总览](#1-功能总览)
- [2. 部署与安装](#2-部署与安装)
- [3. 指令说明](#3-指令说明)
- [4. `说` 命令详解](#4-说-命令详解)
- [5. 多人格配置](#5-多人格配置)
- [6. 语言与翻译机制](#6-语言与翻译机制)
- [7. 角色别名（characters.json）](#7-角色别名charactersjson)
- [8. 缓存机制](#8-缓存机制)
- [9. TTS 默认参数](#9-tts-默认参数)
- [10. 常见问题排查](#10-常见问题排查)
- [11. 致谢与许可](#11-致谢与许可)

---

## 1. 功能总览

| 功能 | 触发方式 | 说明 |
| --- | --- | --- |
| 手动合成 | `说` 命令 | 立即合成指定文本的语音，可指定人格与语言 |
| 自动转语音 | LLM 回复后 | 按 `auto.tts_prob` 概率把 Bot 的回复转成语音发送 |
| LLM 工具调用 | 模型自主 | 注册 `gsv_tts` 工具，由模型决定何时用语音回答 |
| 重启推理服务 | `重启GSV` 命令 | 远程重启 GPT-SoVITS API 进程 |
| 多人格音色 | AstrBot 人格系统 | 不同人格使用不同模型与参考音频 |
| 语言翻译 | 配置或命令指定 | 中文 / 日文 / 英文互转（LLM 翻译后合成） |

## 2. 部署与安装

### 2.1 部署 GPT-SoVITS

1. 部署 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)（建议 v2 及以上）；
2. 参考：[GPT_SoVITS 指南](https://www.yuque.com/baicaigongchang1145haoyuangong/ib3g1e)。

### 2.2 启动 GPT-SoVITS API

在 GPT-SoVITS 根目录启动 api_v2：

```bash
python api_v2.py
```

Windows 可新建 `start_api.bat`：

```bat
runtime\python.exe api_v2.py
pause
```

### 2.3 安装插件

将本插件放入 AstrBot 的 `data/plugins/` 目录（或在插件市场安装原版后用本仓库覆盖），重启 AstrBot。

### 2.4 最小配置

路径：`插件管理 -> astrbot_plugin_GPT_SoVITS -> 插件配置`

| 配置项 | 说明 |
| --- | --- |
| `enabled` | 总开关，打开 |
| `client.base_url` | GPT-SoVITS API 地址，默认 `http://127.0.0.1:9880` |
| `default_params.ref_audio_path` | 默认参考音频（未匹配到人格时使用，插件自带一组默认音频） |

### 2.5 验证

在聊天中发送：

```text
说 你好，我是语音测试
```

收到语音即链路打通。

## 3. 指令说明

| 指令 | 别名 | 说明 |
| --- | --- | --- |
| `说 <内容> [人格] [语言]` | `gsv`、`GSV` | 合成语音，人格与语言参数可选，详见下节 |
| `重启GSV` | `重启gsv` | 请求 GPT-SoVITS 执行重启 |

无需指令的调用方式：

| 方式 | 说明 |
| --- | --- |
| 自动转语音 | Bot 回复后按 `auto.tts_prob` 概率转语音；条件：插件启用、命中概率、文本非空且长度 ≤ `auto.max_msg_len` |
| LLM 工具 `gsv_tts` | 注册给 LLM 的工具，模型可在需要语音输出时自主调用 |

## 4. `说` 命令详解

### 4.1 用法示例

| 用法 | 示例 | 说明 |
| --- | --- | --- |
| `说 <内容>` | `说 你好` | 当前人格音色 |
| `说 <内容> <人格>` | `说 你好 镜华` | 人格名放后面 |
| `说 <人格> <内容>` | `说 镜华 你好` | 人格名放前面 |
| `说 <内容> <人格> <语言>` | `说 你好 镜华 日` | 人格与语言顺序不限 |
| `说 <人格> <内容> <语言>` | `说 镜华 你好 日` | 人格也可在最前 |
| `说 <别名> <内容>` | `说 一歌 你好` | 支持角色别名/昵称/罗马音 |

### 4.2 语言参数

| 写法 | 效果 |
| --- | --- |
| `中文` / `中` | 直接以中文合成 |
| `日文` / `日` | LLM 翻译成日文后合成 |
| `英文` / `英语` / `英` | LLM 翻译成英文后合成 |
| 不指定 | 自动识别内容语言（见 [6.3](#63-自动语言识别)），按输入语言直接合成 |

语言词放在消息**末尾**；显式指定日文/英文时强制走 LLM 翻译，不受全局翻译开关限制；指定中文时跳过翻译。

### 4.3 人格参数

- 人格名可放在正文**之前或之后**，分割点为空格；
- 支持角色别名（`一歌`、`ick` 等，见 [第 7 节](#7-角色别名charactersjson)）；
- 支持含空格的多词人格名（最长优先匹配）；
- 指定的人格若未在 `persona_storage` 中配置语音参数，会提示补充配置；
- 未匹配到人格名的词保留在正文中；剥完参数后正文为空时（如 `说 日`），整条消息按正文朗读。

### 4.4 解析规则

1. 按空格分词；
2. 从**末尾**循环剥离语言词与人格名（两者顺序不限）；
3. 从**开头**剥离人格名（语言词是常用词，为避免误伤正文不支持前置）；
4. 剩余 token 整体作为正文，正文中的空格完整保留。

## 5. 多人格配置

插件将 AstrBot 人格与 GPT-SoVITS 音色绑定：`persona_storage` 中每一项的 `persona_id` 填 **AstrBot 人格名**。

| 字段 | 说明 |
| --- | --- |
| `persona_id` | AstrBot 人格名（即对话当前人格） |
| `gpt_path` | 该人格的 GPT 模型路径（留空沿用当前已加载模型） |
| `sovits_path` | 该人格的 SoVITS 模型路径（留空沿用） |
| `ref_audio_path` | 参考音频路径 |
| `prompt_text` | 参考音频对应文本 |
| `prompt_lang` | 参考音频文本语言 |
| `text_lang` | 合成文本语言（可被命令显式指定或自动识别覆盖） |
| `speed_factor` | 语速倍数 |
| `fragment_interval` | 语音片段间隔 |

模型按需动态切换：不同人格配置了不同模型路径时，合成前自动切换权重，相同模型不会重复切换。

人格名匹配支持 `characters.json` 别名映射（见下一节）。

## 6. 语言与翻译机制

### 6.1 text_lang 优先级

从高到低：

1. 命令显式指定的语言（`中` / `日` / `英文`）
2. 自动识别的语言（`auto_detect_lang` 开启时）
3. 人格配置 `text_lang`
4. 全局翻译配置（`translate.target_lang`）

### 6.2 翻译

| 场景 | 行为 |
| --- | --- |
| 命令指定 `日` / `英文` | 强制 LLM 翻译（不受 `translate.enabled` 限制），内置日译/英译专用提示词 |
| 命令指定 `中文` | 跳过翻译，原文合成 |
| `说` 命令未指定语言 | "输入语言即发音语言"，跳过全局翻译（见 6.3） |
| 自动转语音 / LLM 工具 | `translate.enabled` 开启时先翻译成 `translate.target_lang` 再合成；关闭时按自动识别发音 |

翻译使用 `translate.provider_id` 指定的 LLM Provider，留空则用当前启用的 Provider。

### 6.3 自动语言识别

配置项 `auto_detect_lang`（默认开启）。检测规则：

- 含日文假名（平假名/片假名）→ 日文
- 含 CJK 汉字 → 中文
- 含拉丁字母 → 英文
- 纯数字/符号 → 不设置，沿用人格或默认配置

对三种合成方式均生效。注意：`说` 命令与自动转语音的语言决策语义不同——`说` 命令"输入什么语言就发什么音"，自动转语音"翻译优先、检测兜底"。

## 7. 角色别名（characters.json）

插件目录下的 `characters.json` 提供角色别名表，格式：

```json
[
  {
    "characterId": 1,
    "name": "ick",
    "fullName": "星乃一歌",
    "fullNameChinese": "星乃一歌",
    "aliases": ["小一", "一歌", "一", "炒面面包", "一酱"]
  }
]
```

- 角色的**中文全名、日文全名、罗马音缩写、所有别名**均可用于 `说` 命令指定人格；
- 别名自动映射到 `persona_storage` 中已注册的对应人格名（优先按中文名匹配，其次日文名、缩写）；
- 文件每次调用时重读，修改后无需重启。

## 8. 缓存机制

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| `cache.enabled` | `true` | 相同参数直接复用本地音频 |
| `cache.expire_hours` | `0` | 过期时间（小时），`0` 表示永不过期 |
| `cache.path` | 空 | 留空使用 AstrBot 临时目录 |

- 缓存文件按"请求参数哈希"命名（`gsv_<hash>.<ext>`），参数一致即命中，跳过推理；
- 默认存放于 `data/temp/astrbot_plugin_GPT_SoVITS/`，由 AstrBot 自动清理，不堆积在持久化目录；
- 插件启动时会清扫过期缓存（`expire_hours > 0` 时），并自动清理旧版本默认目录的遗留文件；
- 需要长期保留缓存时，可将 `cache.path` 设置为自定义路径。

## 9. TTS 默认参数

`default_params` 为未命中人格配置时的兜底请求参数（即 GPT-SoVITS `/tts` 接口参数）：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `text_lang` | `zh` | 合成文本语言 |
| `ref_audio_path` | 内置默认音频 | 参考音频路径 |
| `prompt_text` / `prompt_lang` | 与默认音频对应 | 参考音频文本及语言 |
| `text_split_method` | `cut3` | 文本切分方式 |
| `speed_factor` | `1.0` | 语速 |
| `top_k` / `top_p` / `temperature` | `5` / `1.0` / `1.0` | 采样参数 |
| `batch_size` / `batch_threshold` | `1` / `0.75` | 推理批参数 |
| `fragment_interval` | `0.3` | 片段间隔 |
| `seed` | `-1` | 随机种子 |
| `repetition_penalty` | `1.35` | 重复惩罚 |
| `media_type` | `wav` | 输出格式（`wav` / `mp3` / `ogg`） |
| `streaming_mode` / `parallel_infer` / `split_bucket` | `false` / `true` / `true` | 推理开关 |

## 10. 常见问题排查

| 现象 | 排查顺序 |
| --- | --- |
| 提示"当前人格无语音模型文件" | 当前人格未在 `persona_storage` 配置条目，或未绑定任何人格 |
| 提示"人格 xxx 未配置语音参数" | 指定的人格存在但没有 `persona_storage` 条目，按第 5 节补充 |
| `说` 无反应 | 确认 `enabled` 已打开；GPT-SoVITS API 是否启动；`client.base_url` 是否正确 |
| 语音合成失败 | 1) `default_params.ref_audio_path` 文件是否存在；2) 参考音频与模型是否匹配；3) 查看 GSV 端日志 |
| 翻译失败 | `translate.provider_id` 是否指向可用的 LLM Provider |
| 日文发音怪异 | 确认该人格的模型与参考音频为日文训练；检查 `text_lang` 是否被自动识别覆盖（可显式加 `日` 参数） |
| 音色不随人格变化 | 检查人格条目的 `gpt_path` / `sovits_path` 是否有效，GSV 端是否有对应模型文件 |
| 缓存未生效 | 参数（含参考音频、语速等）完全一致才会命中；确认 `cache.enabled` |

查看日志：AstrBot WebUI → 日志，关注 `GPT-SoVITS` 相关条目。

## 11. 致谢与许可

- 原版插件：[Zhalslar/astrbot_plugin_GPT_SoVITS](https://github.com/Zhalslar/astrbot_plugin_GPT_SoVITS)
- 语音合成：[GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)
- 框架：[AstrBot](https://github.com/AstrBotDevs/AstrBot)
- 角色别名数据来自 [Project Sekai](https://pjsekai.com/) 角色资料整理

本项目遵循 [GPL-3.0](./LICENSE) 许可证开源。
