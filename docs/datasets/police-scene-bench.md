# 警务场景模拟评测集（police_scene_bench）

`police_scene_bench@v1-20261028` 用于与鼎桥（td-tech）的验收，按《技术指标_场景分级拆分_鼎桥沟通更新版_20261026》里的“具体使用场景”逐个模拟，每个场景是一个 split，每个 split 100 条，共 83 个。其中 9 个术语场景还各有一个 `-hw300` 版本：音频不变，每条记录多带一份 300 词的热词表。此外附带一份 TTS 听测文本。这个集合只用于评测，不进训练。

配方在 `scripts/police_scene_bench/recipe.yaml`，生成脚本是 `build.py`。split 名按“能力-噪声档-场景”命名，catalog 中每个 split 的说明都写明了对应的表格行号、噪声档和场所。

## 覆盖范围

| 能力 | 表格行（端侧 / 云侧） | split 前缀 | 场景数 | 记录类型 |
|---|---|---|---:|---|
| 通用普通话识别 | 2–6 / 39–43 | `asr-` | 15 | `asr`：短句，或多句长语音（访谈、研讨、接待、口述） |
| GA 行业术语 | 7–11 / 44–48 | `term-` | 9 | `asr`：一句含场景术语的话；`labels.keywords` 是句中出现的术语 |
| 热词 300 个 | 27–31 | `term-*-hw300` | 9 | 音频同 `term-`；`hotwords` 是 300 词列表，包含本 split 用到的全部术语 |
| 号码 | 12–16 / 49–53 | `num-` | 12 | `asr`：手机号、身份证号、车牌、电动车号牌；`labels.number_types` 标明类型 |
| 机主识别 · 分开讲话 | 17–21 / 54–58 | `owner-*-sep-` | 7 | `ts_asr`：注册音频，加上机主与他人轮流说话 |
| 机主识别 · 重叠讲话 | 22–26 / 59–63 | `owner-*-overlap-` | 10 | `ts_asr`：他人与机主同时说话 |
| 角色分离 ≤4 人 | 33–37 / 64–68 | `diar-` | 13 | `speaker_attributed_asr`：按人转写；`labels.segments` 给出每段的起止时间 |
| 角色分离 5–8 人 | — / 64–67 | `diar8-` | 5 | 同上 |
| 上下文矫正 | — / 69–73 | `ctx-` | 6 | `asr`：上下文纠偏评测集的题目放进场景噪声；`labels.context_correction` 沿用原标注 |
| 执法记录仪通道 | 5、9、15、20 等 | `dev-` | 4 | 与原场景逐条配对，只改通道 |
| 设备离人 1–3 米 | 2、17 等 | `far-` | 2 | 与原场景逐条配对，只改通道 |
| TTS 听测文本 | 75 | artifact `tts-eval-texts` | — | 每类 100 条文本：简单句、复杂句、多音字、数字串、专有名词、中英混、对话、≥300 字长段落、情绪（中性、开心、严肃、安抚各 25 条） |

**机主识别**：有三个场景要求“非机主说同样的话不能触发”，即 `owner-light-sep-home-law`、`owner-light-overlap-home-law` 和 `owner-heavy-overlap-security`；极限档 `owner-extreme-overlap-emergency` 也按这个要求做。这些 split 里：

- 30%–40% 的记录中，他人说了与机主相同的句子（`labels.same_text`）。
- 20% 的记录只有他人说话（`labels.owner_present = false`），参考文本为空，期望模型没有输出。

**极限档**：表格里极限档那几行没有写具体场景，统一按事故救援、警笛、暴乱现场模拟，信噪比 −5 到 0 dB，并全部经过执法记录仪通道（见下文）。

**上下文矫正**：按表格行建 split，不按具体场景。题目取自上下文纠偏评测集中与警务相关的四类：警务笔录、报警电话、户籍窗口、物业登记。

## 现有数据没有、另外补的

| 缺什么 | 怎么补 | 脚本 |
|---|---|---|
| 全国 31 省普通车牌、新能源车牌、电动车号牌 | Qwen3-TTS 用 36 个 test 口音说话人克隆合成 470 条，再由 Qwen3-ASR 转写，只保留号牌逐字一致、整句字错率 ≤ 0.3 的 316 条：普通 100、新能源 96、电动车 120。电动车号牌各地格式不同，这里用了两种近似格式（城市名+字母+5 位数字、省简称+城市字母+6 位数字） | `synthesize_plates.py` |
| PDT 对讲机信道 | 用远端手台录到的声音（说话人加远端环境噪声）模拟对讲链路：按下 PTT 后才发射，话筒压限，带宽 300–3400 Hz，经 AMR-NB 4.75–5.9 kbps 或 Speex 低码率编解码，20 ms 帧丢失 0–5%，松开后有静噪尾音，一半样本带结束提示音。PDT 的声码器没有开源实现，所以用同类低码率窄带编解码代替 | `build.py` 的 `radio_link` |
| 执法记录仪实机录音 | 近似模拟三点：现场声压过高时话筒或 ADC 削波（极限档削掉峰值 3–12 dB，重度档 0–6 dB），然后高通 100–200 Hz，最后自动增益（目标 −22 dBFS，±20 dB）。没有实机的频响，也模拟不了人在噪声里不自觉提高嗓门 | `build.py` 的 `recorder_chain` |
| 2 米左右远场（如 BUG-08） | 民警语音也加上所在房间的实测冲激响应 | `far_field` |
| TTS 听测文本 | 用 AmphionData 的在线 LLM（doubao-seed-2-0-pro）按类别生成，再做程序检查：长度、多音字标注、数字串、英文、对话格式。MOS 仍需人工听测 | `generate_tts_texts.py` |
| 法条检索指令 | 数据里没有；用查询类业务语句（查一下、帮我查等）和引用法条的语句代替 | 配方 `law_query` 池 |

性能项（内存、并发、首尾包时延）不需要专门数据，任何 split 的音频都可以拿来测。

## 怎么模拟

- **说话人**：佩戴设备的民警离麦克风很近，不加混响；多人场景里的 S1、机主场景里的机主都是这位民警。其他在场人员离设备 1–2 米，电平比民警低 0–6 dB，并加上所在场所的 MIT 实测冲激响应：办公室、家中、车内、商店、大厅或户外。
- **噪声**：
  - 先铺一层 DEMAND 环境录音，如轿车、街道、厨房、餐馆、广场；
  - 再按场所随机放 FSD50K 评测划分的事件声，如警笛、鸣笛、风噪、电钻、音乐、人群喊叫；
  - 街面、人群、主干道等场所还会叠加中文背景人声，取自 `asr_babble_bench` v2，说话人来自 KeSpeech test，不进训练。
- **信噪比**：按表格 F 列分档。安静 20–30 dB，轻度 10–20 dB，中度 5–10 dB，重度 0–5 dB，极限 −5–0 dB。计算方式是民警语音电平（−25 dBFS）减去整段噪声电平。对讲链路场景里，这个信噪比指的是远端手台处的信噪比。
- **语音来源**：警务统合版 `police_asr_unified@v1-20261009` 的 test 划分。只有短句文本池不够用时才补 dev 划分，两者都不进训练。号牌另用上面新合成的那批。同一 split 内，同一段语音只用一次；同一文本最多出现 3 次，且由不同说话人说。多人对话和机主场景只用 test 划分的 158 个说话人。

## 使用边界

- 语音全部是 TTS 合成（Qwen3-TTS 等），只做过自动质检，没有人工听审。模拟结果只用于内部定位问题，不能代表现场验收。
- 多人对话由不同说话人的独立句子拼成，内容不连贯。可以用来评测角色分离和转写在声学上的难度，不能用来评测语义理解。
- 对讲链路和执法记录仪通道都是近似模拟，与真实手台和真实设备的差距没有校准过。
- 号码文本的种类少：身份证号只有约 70 种，警务数据中的车牌约 290 种。同一号码会由不同说话人重复说。

## 读取

```bash
audio-data-contract resolve catalog police_scene_bench v1-20261028 records --roots roots.json  # 按 split 取 records
```

roots 中的 `police_scene_bench` 指向 `/workspace/data/datasets/police_scene_bench`。

- 音频路径在 `audio-index` 里，记录中 `audio_slots[].ref.cut_id` 对应它的一行。
- `ts_asr` 记录有两个槽：`enrollment` 和 `mixture`。
- TTS 听测文本在 artifact `tts-eval-texts`（JSONL），字段有 `category`、`text`；多音字类另有 `polyphones`，专有名词类另有 `nouns`，情绪类另有 `emotion`。

## 重新生成

```bash
python scripts/police_scene_bench/synthesize_plates.py jobs            # 之后 tts（qwen-tts 环境）、asr（含 qwen-asr 的环境）、qc、export
python scripts/police_scene_bench/generate_tts_texts.py                 # 需要 AmphionData 和 ~/amphionkeys 的方舟密钥，见脚本说明
PYTHONPATH=src python scripts/police_scene_bench/build.py --roots /workspace/data/registry/roots.json --workers 64
```

脚本不会覆盖已存在的版本；改配方时先改 `recipe.yaml` 里的 `version`。做冒烟测试时加 `--limit 3 --no-register`，并把 roots 里的 `police_scene_bench` 指到临时目录（目录里要有 `tts/` 的链接）。
