#!/bin/bash
# 每小时把 DATA-TTS-UNIFIED 的正式发布（PUBLICATIONS.md“当前发布总览”）同步到共享 registry。
# 容器内没有 systemd/cron，用此循环代替；以 mingdong 运行，容器重启后需重新启动。
# 运行中的 bash 会边执行边读脚本，所以运行部署副本，不直接运行仓库里的文件：
#   install -D deploy/tts-unified-sync.sh /workspace/data/tts-unified-sync/sync.sh
#   setsid nohup bash /workspace/data/tts-unified-sync/sync.sh \
#     >> /workspace/data/tts-unified-sync/sync.log 2>&1 < /dev/null &
# ADC_SRC 是要使用的 audio-data-contract 源码目录，默认为主仓库。
set -u
export TZ=Asia/Shanghai
export PYTHONPATH=${ADC_SRC:-/workspace/data/audio-data-contract/src}
PY=${PY:-/workspace/workspace/mingdong/miniconda3/envs/adc-dev/bin/python}
REGISTRY=/workspace/data/registry
STATE=/workspace/data/tts-unified-sync/alert.state
# 失败告警复用 storage-audit 的飞书 webhook；它只在 root 可读的文件里，启动时读进环境变量。
set -a; . <(sudo -n cat /etc/storage-audit.env); set +a

while true; do
  echo "$(date '+%F %T') sync start"
  "$PY" -m audio_data_contract.cli sync-tts-unified /workspace/data \
    --catalog-dir "$REGISTRY/catalog" --views "$REGISTRY/views" \
    --roots "$REGISTRY/roots.json" --notify --state "$STATE"
  echo "$(date '+%F %T') sync exit $?"
  sleep 3600
done
