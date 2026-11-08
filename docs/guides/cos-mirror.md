# 已登记数据的 COS 镜像（ab）

每个已登记的数据目录都在 COS 上保留一份可以直接 `ab pull` 的副本。COS 路径就是本机 `/workspace/data/` 下的相对路径：

```text
amphion-audio-backup-1373259071:audio-data-contract/<本机 /workspace/data/ 下的路径>/
```

例如 `/workspace/data/datasets/emilia2/` 对应 `audio-data-contract/datasets/emilia2/`。已核对的目录和版本记录在 [ab-mirror.json](../../catalog/backups/ab-mirror.json)。

## 范围

- 已登记版本的产物所在目录，判定规则和存储巡检一致：`datasets/<id>/<子目录>/<版本>`、`DATA-TTS-UNIFIED/datasets/<id>/<release>`，以及数据集有已登记版本时它的 `source/`。
- catalog 没有列出、但被已登记版本的 manifest 直接引用的目录，写在 [deploy/cos-mirror.sh](../../deploy/cos-mirror.sh) 的 `INCLUDE` 里。
- COS 上已有相同副本的不再上传：
  - `DATA-TTS/WenetSpeech-{Yue,Chuan,Wu}` 在 TTS 桶 `amphion-tts-data-1373259071:WenetSpeech-{Yue,Chuan,Wu}/`（2026-11-04 核对，文件名和总大小一致）。
  - [噪声镜像](noise-data-mirror.md)中换了名字的目录沿用原位置，例如 `DATA-TTS/dns5` 在 `datasets/dns5_noise_rir/`。
- 不包括评测运行目录（`ae-runs`）、训练输出和未登记目录。

## 同步方式

[deploy/cos-mirror.sh](../../deploy/cos-mirror.sh) 循环运行 [scripts/cos_mirror.py](../../scripts/cos_mirror.py)，每轮分三步：

1. `plan` 从 registry 算出要同步的目录，以及每个版本用到哪些目录。
2. `push` 逐个目录比较本机文件和 COS 对象的路径与大小，只上传 COS 上缺少的文件，上传时调用 ab 自己的 `push_one`。同名但内容不同的文件按冲突报告，已有对象不覆盖、不删除。
3. 没有冲突和失败的目录记为已核对；一个版本用到的目录全部核对后，才写进记录。

每轮结束后隔一天再开始下一轮，新登记的数据在下一轮补传。已登记版本的文件不会原地修改，所以路径和大小都相同的文件不再读取内容比对。

### 小文件先打包再上传

小于 8 MiB 的文件不逐个上传：逐个请求会让带宽用不满，yodas 一类上百万个 100 KB 左右的 wav 只有约 25 MiB/s。`push` 把 COS 上缺的小文件按路径顺序交给系统的 GNU `tar` 打包（不用 Python 打包，Python 单进程会把一个核跑满），`tar` 的输出通过管道按 32 MiB 一块直接做 COS 分片上传，只在内存里，不在本机落盘；默认同时打 16 个分片，每个约 4 GiB。每个分片在 `<目录>.packed/` 下有 `<id>.tar` 和 `<id>.json.gz`，后者列出成员路径和大小，在 tar 传完后才写入；成员以索引为准判断是否已在 COS 上，所以重跑不会重复打包。大于 8 MiB 的文件照旧单独上传。

`--pack-below 0` 会被拒绝，需要同时加 `--allow-small-files`。2026-11-07 之前已逐个上传的目录（yodas_de、yodas_es、yodas_ko 等）保持原样，不重传。

首轮从小目录开始传。本机上传到 COS（广州）约 60 MiB/s，2026-11-04 实测增加并发也没有更快，因此首轮要传两周左右。2026-11-08 实测：改用 GNU tar 后上行稳定在 43–59 MiB/s，和这条链路的上限一致。上传会占满出口带宽，需要时用 `WORKERS` 调低并发。

## 记录与日志

| 文件 | 内容 |
|---|---|
| `/workspace/data/cos-mirror/ab-mirror.json` | 每核对完一个目录就更新：已核对的目录（文件数、字节数、核对日期），以及目录全部核对过的版本 |
| `/workspace/data/cos-mirror/state.json` | 每个目录最近一次的结果，包括冲突、失败和 COS 上多出的对象数 |
| `/workspace/data/cos-mirror/mirror.log` | 每个目录一行结果，每 10 分钟一行上传进度 |

仓库里的 [ab-mirror.json](../../catalog/backups/ab-mirror.json) 是实时记录的快照，数据总览的 COS 列读这一份。更新时把实时记录复制过来，运行 `audio-data-contract generate-overview` 后提 PR。

## 部署

容器内没有 systemd/cron，用循环脚本代替；以 mingdong 运行，容器重启后需重新启动：

```bash
install -D deploy/cos-mirror.sh /workspace/data/cos-mirror/mirror.sh
install -D scripts/cos_mirror.py /workspace/data/cos-mirror/cos_mirror.py
install -D -m 644 catalog/backups/ab-noise.json /workspace/data/cos-mirror/ab-noise.json
setsid nohup bash /workspace/data/cos-mirror/mirror.sh \
  >> /workspace/data/cos-mirror/mirror.log 2>&1 < /dev/null &
```

检查是否在运行：`ps -eo pid,cmd | grep "[c]os-mirror/mirror.sh"`。

## 拉取

单独上传的文件用 ab 拉取：

```bash
ab pull amphion-audio-backup-1373259071:audio-data-contract/datasets/emilia2/ /data/datasets/emilia2/
```

打包的小文件用 `unpack` 流式读取分片并解压，不先把 tar 存到本机；已有同名同大小的文件会跳过，分片和索引不一致时返回非零：

```bash
$AB_PY scripts/cos_mirror.py unpack datasets/emilia2 --target /data/datasets/emilia2
```

一个目录里可能两种都有，两条命令都要跑。完整规则和命令见 [skills/cos-pack-sync/SKILL.md](../../skills/cos-pack-sync/SKILL.md)。

拉到 `<目标>/` 下保持同样的相对路径后，目录结构和本机 `/workspace/data/` 一致。Lhotse 清单和音频索引里写的是本机绝对路径（`/workspace/data/...`），换机器使用时把这个前缀换成 `<目标>/`；`roots.json` 中的根目录同样替换。
