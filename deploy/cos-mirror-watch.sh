#!/bin/bash
# 看门狗：保证 mirror.sh 在运行，失败后自动拉起。
# - mirror.sh 不在了（被杀、进程退出）：重新启动。
# - 某一轮崩溃（"round exit" 非 0，且该轮没有打印正常结束的 "done;" 行）：等 BACKOFF 秒后重启。
#   push 幂等，重启只补传缺的部分。push 正常跑完但有冲突或失败的目录（有 "done;" 行）不重启，下一轮照常隔一天再跑。
# 容器内没有 systemd/cron，容器重启后本脚本和 mirror.sh 都需重新启动：
#   install -D deploy/cos-mirror-watch.sh /workspace/data/cos-mirror/watch.sh
#   setsid nohup bash /workspace/data/cos-mirror/watch.sh >> /workspace/data/cos-mirror/watch.log 2>&1 < /dev/null &
set -u
# 上传必须直连 COS，不经过会话的本机代理（它会让分片上传卡住超时）。
unset https_proxy HTTPS_PROXY http_proxy HTTP_PROXY all_proxy ALL_PROXY
WORK=${WORK:-/workspace/data/cos-mirror}
BACKOFF=${BACKOFF:-600}
INTERVAL=${INTERVAL:-60}
LOG=$WORK/mirror.log

running() { pgrep -f "^bash $WORK/mirror.sh" | head -1; }

launch() {
  echo "$(date '+%F %T') watch: starting mirror.sh ($1)"
  setsid nohup bash "$WORK/mirror.sh" >> "$LOG" 2>&1 < /dev/null &
}

crashed() {  # the latest round ended with a non-zero exit and never reached "done;"
  local round
  round=$(awk '/ round start$/{r=""} {r=r"\n"$0} END{print r}' "$LOG")
  grep -qE ' round exit [1-9][0-9]*$' <<< "$round" && ! grep -q ' done; ' <<< "$round"
}

while true; do
  pid=$(running)
  if [ -z "$pid" ]; then
    launch "not running"
  elif crashed; then
    echo "$(date '+%F %T') watch: last round crashed; restarting in ${BACKOFF}s"
    pkill -P "$pid" 2>/dev/null; kill "$pid"
    sleep "$BACKOFF"
    launch "retry after crash"
  fi
  sleep "$INTERVAL"
done
