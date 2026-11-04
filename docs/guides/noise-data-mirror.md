# 噪声与 RIR 数据镜像（ab）

已登记的噪声和冲激响应（RIR）数据集在 COS 上各有一份可以直接 `ab pull` 的副本，记录在 [ab-noise.json](../../catalog/backups/ab-noise.json)：

```text
amphion-audio-backup-1373259071:audio-data-contract/datasets/<目录>/
```

- `directories`：每个 COS 目录对应的本机目录（`local`）。目录原样上传，COS 上的相对路径和本机相同。`voices` 只上传了噪声部分（`only` 所列子目录）；`dns5_noise_rir` 对应本机 `/workspace/data/DATA-TTS/dns5/`。
- `datasets`：每个版本所在的目录（`alias`）。`requires` 列出还要一起拉取的目录，例如 `wham@tr-20261014` 只有清单，音频在 `noise_open`。
- 2026-11-03 首次同步 25 个版本、19 个目录（50.7 万个文件，367 GiB），逐个比对了文件名和大小。
- RealMAN（`realman@hf-aishell-20261025`）是阵列语音语料，2026-11-04 先上传了其中的纯噪声：train、val_raw、test_raw 下的 `ma_noise`（27.7 万个文件，449 GiB），记在 `directories.realman`。这个版本的语音部分由[全部已登记数据的镜像](cos-mirror.md)补传，全部核对后才会出现在记录的版本列表里。

## 拉取

```bash
ab pull amphion-audio-backup-1373259071:audio-data-contract/datasets/noise_open/ /data/datasets/noise_open/
```

拉到 `<目标>/datasets/<目录>/` 后，目录结构和本机 `/workspace/data/datasets/` 一致。Lhotse recordings 清单里写的是本机绝对路径（`/workspace/data/datasets/...`），换机器使用时要把这个前缀换成 `<目标>/datasets/`。

## 新增噪声或 RIR 数据集

新登记的数据会由[全部已登记数据的镜像](cos-mirror.md)自动补传。需要马上单独上传时，登记后上传它的目录，再用 `--dry-run` 确认没有待传、冲突或失败的文件，然后在 `ab-noise.json` 补上目录和版本，运行 `audio-data-contract generate-overview`：

```bash
ab push /workspace/data/datasets/<目录>/ amphion-audio-backup-1373259071:audio-data-contract/datasets/<目录>/
ab --json push /workspace/data/datasets/<目录>/ amphion-audio-backup-1373259071:audio-data-contract/datasets/<目录>/ --dry-run
```
