# 四个 agent 固定分组传输

本轮交接目录：`state/aidc-20260923/shards/`。A 是现有环境；另外三个 Docker 分别只认领 B、C、D 中的一个。不要让两个 agent 使用同一个编号。

## 归属

现有迁移数据库的 `object_id` 是唯一文件编号。已经完成的对象不重传；启用分组前已入队的所有批次留给 A。新入队对象按以下规则处理：

| agent | 范围 |
|---|---|
| A | 清单和 JSON/JSONL 文件、超过默认 8 GiB 的文件及其全部分块，以及其余对象 `object_id % 4 == 0` |
| B | 其余对象 `object_id % 4 == 1` |
| C | 其余对象 `object_id % 4 == 2` |
| D | 其余对象 `object_id % 4 == 3` |

A 独占原数据库、扫描、批次导出、回执导入、大文件组装及最终 registry 发布。B/C/D 只读各自 `plans/` 中的不可变清单，不自行扫描、建批次、修改源文件或执行 finalize。

`batch_agents` 固定新批次的归属；缺少归属记录的旧批次仍由 A 负责。外部批次在主数据库中保持 `external`，只有 A 从目标端重新获取、核对回执和源文件签名后才登记完成。外部批次未完成时不会进入最终发布。

## 新 Docker 启动

先检查本 Docker 能以原绝对路径读取清单中的公盘文件、能用 `ssh aidc-dev` 连接目标，且有 Python 3.10 或更新版本。代码和所需 Python 模块已固定在交接目录的 `runtime-v1/`，不要依赖项目 `.venv` 的跨机器可用性。

例如 B：

```bash
bash /222042021/mingdong/workspace/audio-data-contract/state/aidc-20260923/shards/agent-b/start.sh \
  --local-state /tmp/aidc-agent-b \
  --workers 128
```

C/D 将命令中的 `agent-b` 换成自己的编号。`128` 是可调整的本容器并发参数，不是全局配额或代码上限。各 agent 根据本机吞吐和资源自行调整；其他组无需同步修改。日志和进程托管配置放本 Docker 本地，用本地 supervisor 或其他进程托管方式保持运行。

同一 agent 在 aidc-dev 上持有独占锁，重复启动会报错退出，不要删除锁文件绕过。重启前确认旧进程及其子进程已退出；保留本地状态目录。worker 会自动复用远端已完成批次回执，重试临时网络错误，内容或源文件错误留在 `errors/` 中供处理。

## 公盘协作规则

- 不运行项目原来的 `init`、`run`、`watch`、`scan`、`transfer`、`finalize`。
- 不打开或修改主任务 `migration.sqlite` 及 WAL，不复用主任务的 supervisor、PID 或 socket。
- 不编辑 `runtime-v1/`、`worker.json`、归属文件和任何 `plans/`；不操作其他 agent 的目录。
- 只按分配的目标路径传输；B/C/D 的 run 分别为 `aidc-20260923-b/c/d`，临时文件和远端回执与 A 隔离。
- 公盘交接目录中，本 agent 只写 `results/`、`errors/` 和 `progress.json`。A 将核验后的回执移入 `imported/`。
- 源文件应只读挂载。worker 检查大小和修改时间，并检查一次读取期间的本地文件身份；跨挂载 device/inode 不要求与 A 相同。传输计划不改写，内容仍执行 SHA-256 校验。
- 新清单持续由 A 导出；目录暂时为空不代表整个任务完成。worker 保持等待，最终停止由统一验收结果决定。

## 查看进度

各组读取自己交接目录的 `progress.json` 和 `errors/`。全局进度读取主任务 `progress.json`；`external` 表示已交给 B/C/D、尚未导入成功回执的批次，不等同于传输失败。

扫描异常仍按原流程记录，不会因为分组被跳过或标记成功。整个任务仍需最后的统一校验。
