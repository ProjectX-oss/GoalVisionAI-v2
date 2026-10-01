#!/usr/bin/env bash
# Operator-run, read-only diagnostic. No restart, deployment, or provider call.
set -u
umask 077
gv_spy=/home/arvis/.cache/uv/archive-v0/yI0W7uZMUy2__eeD/bin/py-spy
if [ ! -x "$gv_spy" ]; then
  echo "DIAGNOSTIC_TOOL_UNAVAILABLE"
  exit 1
fi
sudo -v || exit 1
gv_diag="$(mktemp /home/arvis/goalvision-operations/discovery-cpu-20261001-XXXXXX.txt)" || exit 1
gv_success=0
for gv_sample in 1 2 3; do
  echo "Diagnostika: $gv_sample/3"
  gv_pid="$(systemctl show goalvision-lab-v2-discover.service --property=MainPID --value 2>>"$gv_diag")"
  {
    date -u
    if [[ "$gv_pid" =~ ^[1-9][0-9]*$ ]]; then
      ps -p "$gv_pid" -o pid,stat,etime,pcpu,wchan:30
      if timeout 15s sudo -n "$gv_spy" dump --pid "$gv_pid" --nonblocking; then
        gv_success=$((gv_success + 1))
      fi
    else
      echo "DISCOVERY_NOT_RUNNING"
    fi
  } >>"$gv_diag" 2>&1
  if [ "$gv_sample" -lt 3 ]; then sleep 5; fi
done
printf 'STACK_SAMPLES=%s\nDIAGNOSTIC_SAVED=%s\n' "$gv_success" "$gv_diag"
