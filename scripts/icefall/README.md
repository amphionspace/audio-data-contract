# Icefall 数据准备工具

本目录拥有数据下载、清洗、划分、manifest 规整、特征/噪声/评测集生成和准备流水线。
Icefall 只保留历史命令的软链或转发入口；修改实现及相应测试应在本仓库进行。

安装独立语料准备依赖：

```bash
python -m pip install -e '.[preparation,dev]'
python scripts/icefall/download_realman_asr.py --help
python scripts/icefall/prepare_farfield_manifests.py --help
pytest tests/preparation -q
```

RealMAN 需要额外安装 aria2c 和 7zz（可通过命令行指定路径）。下载重启时会对
已存在的 LFS 文件执行 SHA-256 校验，因此大语料需要等待顺序磁盘读取；校验成功
的文件在本进程内不重复读取。失败保留分片，成功后继续解包并生成清单。

独立下载、官方数据清单、police 划分和文本筛选不依赖 icefall。
旧 recipe 的噪声混合、分片、文本规范和 fbank 工具需要复用 icefall 的 cut
加载器或模型侧依赖；通过 `--icefall-root /path/to/icefall` 显式指定 checkout。
作为 icefall submodule 运行时可自动定位。准备流水线始终接收该参数：

```bash
bash scripts/icefall/zh_en/prepare_from_lhotse.sh \
  --icefall-root /path/to/icefall --stage 17 --stop-stage 17
```

这些兼容流水线可调用 icefall 的上游 recipe 或词表构建程序，相应依赖（k2、
文本归一化库等）仍需按模型项目安装。模型训练和 checkpoint 处理由 icefall 维护。
