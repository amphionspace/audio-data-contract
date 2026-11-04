#!/bin/bash
# 把已登记的数据目录同步到 COS（只补传缺的文件，不覆盖、不删除），每轮结束后写出已核对的目录与版本，隔一天再跑下一轮。
# 容器内没有 systemd/cron，用此循环代替；以 mingdong 运行，容器重启后需重新启动。
# 运行中的 bash 会边执行边读脚本，所以运行部署副本：
#   install -D deploy/cos-mirror.sh /workspace/data/cos-mirror/mirror.sh
#   install -D scripts/cos_mirror.py /workspace/data/cos-mirror/cos_mirror.py
#   install -D -m 644 catalog/backups/ab-noise.json /workspace/data/cos-mirror/ab-noise.json
#   setsid nohup bash /workspace/data/cos-mirror/mirror.sh \
#     >> /workspace/data/cos-mirror/mirror.log 2>&1 < /dev/null &
# ADC_SRC 是计算登记目录时使用的 audio-data-contract 源码目录，默认为主仓库。
set -u
export TZ=Asia/Shanghai
WORK=/workspace/data/cos-mirror
ADC_SRC=${ADC_SRC:-/workspace/data/audio-data-contract/src}
PY=${PY:-/workspace/workspace/mingdong/miniconda3/envs/adc-dev/bin/python}
# 上传用 AmphionBucket 自带的 Python 环境，调用 ab 自己的 push_one。
AB_PY=${AB_PY:-/workspace/workspace/mingdong/.local/share/amphion-bucket/venv/bin/python3.12}
# ab 每个文件的续传目录放在本机盘，不放在共享盘上。
export AMPHION_BUCKET_STATE_DIR=${AMPHION_BUCKET_STATE_DIR:-/tmp/cos-mirror-ab-state}
# catalog 不直接列出、但被已登记版本的 manifest 引用的目录（见 storage-zones.yaml）。
# DATA-TTS/WenetSpeech-{Yue,Chuan,Wu} 不在这里：TTS 桶同名目录已有一份相同的（文件名与总大小一致）。
INCLUDE=(
  /workspace/data/datasets/farfield_speech_noise
)

while true; do
  echo "$(date '+%F %T') round start"
  PYTHONPATH=$ADC_SRC "$PY" "$WORK/cos_mirror.py" plan \
    "${INCLUDE[@]/#/--include=}" \
    --known "$WORK/ab-noise.json" \
    --output "$WORK/plan.json" \
  && "$AB_PY" "$WORK/cos_mirror.py" push "$WORK/plan.json" \
    --state "$WORK/state.json" --ledger "$WORK/ab-mirror.json" --workers "${WORKERS:-64}"
  echo "$(date '+%F %T') round exit $?"
  sleep 86400
done
