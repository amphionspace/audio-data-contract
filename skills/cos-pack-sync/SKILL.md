---
name: cos-pack-sync
description: 把本机数据目录同步到 COS，或把 COS 上的目录拉回本机。小文件（wav/flac 等）必须先流式打成 tar 分片再上传，拉回时流式解压；用户提到上传/备份/镜像/恢复数据目录到对象存储、COS、ab push、ab pull 时使用。不要对含大量小文件的目录直接 ab push。
---

# COS 打包上传与解压下载

**规则：小文件不得逐个上传。** 小于 8 MiB 的文件一律先打进 tar 分片，再用 COS 分片上传发出；一次请求一个文件会让带宽用不满（实测 yodas 约 25 MiB/s，且请求数以百万计）。打包在内存里流式完成，不在本机落盘，不占额外存储。

## 上传（打包 → 上传）

只用 `scripts/cos_mirror.py push`，不要对数据目录直接 `ab push`：

```bash
AB_PY=/workspace/workspace/mingdong/.local/share/amphion-bucket/venv/bin/python3.12
$AB_PY scripts/cos_mirror.py push plan.json --state state.json --ledger ab-mirror.json
```

- `plan.json` 由 `scripts/cos_mirror.py plan` 从 registry 生成；日常由 `deploy/cos-mirror.sh` 循环调用，已登记的数据不需要手动传。
- 默认值：`--pack-below 8MiB`、`--shard-size 4GiB`、`--part-size 32MiB`。大于 8 MiB 的文件仍单独上传。
- `--pack-below 0` 会被拒绝；确实要逐个传小文件，必须加 `--allow-small-files` 并说明理由。
- 内存占用约 `packers × (part-inflight + 1) × part-size`，默认约 2.5 GiB，本机不落盘。
- 幂等：重跑只补传缺的文件；已在分片索引里的文件算已存在。

COS 上的布局：

```text
<prefix><相对路径>/                 单独上传的大文件（路径同本机）
<prefix><相对路径>.packed/<id>.tar        分片
<prefix><相对路径>.packed/<id>.json.gz    分片索引（成员路径与大小），在 tar 完成后才写入
```

没有索引的 tar 不被信任，下一轮会重新打包。

## 下载（拉回 → 解压）

```bash
# 小文件：流式读取分片并解压，不先把 tar 下载到本机
$AB_PY scripts/cos_mirror.py unpack datasets/yodas_es/source --target /data/yodas_es
# 大文件：照旧用 ab
ab pull amphion-audio-backup-1373259071:audio-data-contract/datasets/yodas_es/source/ /data/yodas_es/
```

- `unpack` 把每个分片按索引逐个核对大小，目标里已有同名同大小的文件会跳过；索引里的文件在 tar 里找不到时报错并返回非零。
- `--only <子目录>/` 只解压部分子目录；`--dest` 用于换过名字的镜像目录（见 `docs/guides/cos-mirror.md`）。
- 目标目录里要同时有大文件和小文件，两条命令都要跑。

## 检查

- 上传后 `state.json` 里该目录的 `ok` 为 true，`failed`、`conflict` 为 0；`packed` 是打包文件数，`shards` 是分片数。
- 不要手工删除或改名 `.packed/` 下的对象。
