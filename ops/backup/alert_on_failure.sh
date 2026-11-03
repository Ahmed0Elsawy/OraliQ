#!/bin/sh
# Called by oraliq-db-backup-alert@.service when the backup unit fails (including when it could not
# even start, which oraliq_db_backup.py itself cannot report). Passes the unit name and its last
# log lines to BACKUP_ALERT_COMMAND. The backup tool already redacts its own log lines.
set -u
UNIT="${1:-oraliq-db-backup.service}"
LINES="$(journalctl -u "$UNIT" -n 20 --no-pager -o cat 2>/dev/null | tail -n 20)"
if [ -z "${BACKUP_ALERT_COMMAND:-}" ]; then
    echo "oraliq backup FAILED ($UNIT) and BACKUP_ALERT_COMMAND is not set" | systemd-cat -t oraliq-backup -p err
    exit 1
fi
# shellcheck disable=SC2086  # the command is a word list on purpose
exec $BACKUP_ALERT_COMMAND FAILED "systemd unit $UNIT failed. Last lines: $LINES"
