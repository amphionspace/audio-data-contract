# 新集群本地注册盘点（2026-09-24）

已发布 `dns5_noise_rir@official-noise-rir-20260924`，包含 DNS5 官方噪声与脉冲响应脚本列出的全部 10 个归档。`/workspace/data/registry` 现有 1 个可用版本、0 个 View。其余数据暂不发布。

| 范围 | 本轮结论 | 依据与缺口 |
|---|---|---|
| DNS5 噪声与脉冲响应 | 已登记，10 个文件，共 40,491,427,807 字节 | 与[官方脚本](https://github.com/microsoft/DNS-Challenge/blob/master/download-dns-challenge-5-noise-ir.sh)的文件清单逐项一致；Azure 文件大小匹配；每个文件完成本地 SHA-256、`bzip2 -t` 和 tar 内容抽查。逐文件结果见 [dns5-noise-rir-files.jsonl](dns5-noise-rir-files.jsonl)。官方未提供可直接核对的完整归档哈希。 |
| Emilia-YODAS DE | 未登记 | 与[官方 DE 目录](https://huggingface.co/datasets/amphion/Emilia-Dataset/tree/main/Emilia-YODAS/DE)的 161 个文件名、大小一致，但 `DE-B000049.tar` 的本地 SHA-256 与官方目录安全扫描链接中的哈希不同；其余 160 个匹配。须修复该文件后重验。逐文件结果见 [emilia-yodas-de-files.jsonl](emilia-yodas-de-files.jsonl)。 |
| Emilia-YODAS EN | 未登记 | 盘点时官方目录有 1,362 个 tar，本地完整 tar 为 963 个，缺 399 个，另有 46 个 `.part` 文件；传输仍在进行。 |
| HiFiTTS2 原始下载 | 未登记 | 下载 URL 清单共 149,032 条，本地对应文件 146,578 个，缺 2,454 个。 |
| 仓库历史版本 | 未登记 | 原有 362 个版本中，354 个没有本地版本目录；另 8 个只落地部分文件，共缺 61 个声明产物。历史声明保留在仓库。 |

完整缺口见 [catalog-gaps.jsonl](catalog-gaps.jsonl) 和 [external-gaps.json](external-gaps.json)；扫描范围和文件数见 [data-scan.json](data-scan.json)。扫描排除了 `.incoming/`、传输辅助目录、仓库自身和迁移工作目录。历史版本的部分落地文件仅记录位置、大小及仓库预期校验值，不视为已验证。EN 的数字是报告中的时间点快照，传输完成后需重扫。

本轮发布的产物都是源归档，没有待解析的外部音频路径清单；[unresolved-references.json](unresolved-references.json)记录了这一检查范围。原迁移工作目录中的清单没有作为可用版本发布。

注册表先在候选目录加载并检查全部 10 个产物路径与大小，抽查两个产物的 SHA-256，之后原子替换空的 `/workspace/data/registry`。[registry-publish.json](registry-publish.json)记录发布结果。仓库及本地注册表均通过 `validate-catalog`、`validate-views`；数据总览通过 `generate-overview --check`。随后用 CLI 完成 `resolve` 与 `verify-artifact` 抽查。

后续传输完成后，按此报告重扫缺失文件，核对官方清单与校验值；只有版本全部声明产物存在、校验通过且样本清单中的实际文件引用能在新集群解析时，才把该版本及其两端均可用的 View 放入本地注册表。

> 2026-10-03 补注：本机数据后来重排，这 10 个归档移到 `/workspace/data/DATA-TTS/dns5/`，大小与 SHA-256 不变。声明改用专属根目录别名 `dns5_noise_rir` 指向归档目录本身，相对路径只剩文件名；集群差异由本机 `roots.json` 吸收，本报告其余路径为 09-24 快照。
