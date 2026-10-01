#!/bin/bash
set -eu
umask 077
sudo -v
gv_report=$(mktemp /home/arvis/goalvision-operations/admin-diagnostic-20261001-XXXXXX.json)
if sudo -n /usr/bin/python3 -I /home/arvis/goalvision-operations/admin-diagnostic-20261001/inspect.py >"$gv_report"; then
    printf 'ADMIN_DIAGNOSTIC_SAVED=%s\n' "$gv_report"
else
    printf 'ADMIN_DIAGNOSTIC_FAILED=%s\n' "$gv_report"
    exit 1
fi
