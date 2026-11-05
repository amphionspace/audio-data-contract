# 噪声与 RIR 数据镜像（ab）

已登记的噪声和冲激响应（RIR）数据集在 COS 上各有一份可以直接 `ab pull` 的副本，记录在 [ab-noise.json](../../catalog/backups/ab-noise.json)：

```text
amphion-audio-backup-1373259071:audio-data-contract/datasets/<目录>/
```

- `directories`：每个 COS 目录对应的本机目录（`local`）。目录原样上传，COS 上的相对路径和本机相同。`voices` 只上传了噪声部分（`only` 所列子目录）；`dns5_noise_rir` 对应本机 `/workspace/data/DATA-TTS/dns5/`。
- `datasets`：每个版本所在的目录（`alias`）。`requires` 列出还要一起拉取的目录，例如 `wham@tr-20261014` 只有清单，音频在 `noise_open`。
- 2026-11-03 首次同步 25 个版本、19 个目录（50.7 万个文件，367 GiB），逐个比对了文件名和大小。RealMAN 虽带 `noise` 标签，但它是 766 GiB 的阵列语音语料，没有包含在内。

## 拉取

```bash
ab pull amphion-audio-backup-1373259071:audio-data-contract/datasets/noise_open/ /data/datasets/noise_open/
```

拉到 `<目标>/datasets/<目录>/` 后，目录结构和本机 `/workspace/data/datasets/` 一致。Lhotse recordings 清单里写的是本机绝对路径（`/workspace/data/datasets/...`），换机器使用时要把这个前缀换成 `<目标>/datasets/`。

## 新增噪声或 RIR 数据集

登记后上传它的目录，再用 `--dry-run` 确认没有待传、冲突或失败的文件，然后在 `ab-noise.json` 补上目录和版本，运行 `audio-data-contract generate-overview`：

```bash
ab push /workspace/data/datasets/<目录>/ amphion-audio-backup-1373259071:audio-data-contract/datasets/<目录>/
ab --json push /workspace/data/datasets/<目录>/ amphion-audio-backup-1373259071:audio-data-contract/datasets/<目录>/ --dry-run
```
