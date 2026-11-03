# OralIQ database backup and restore

Production backups of the OralIQ PostgreSQL database, for a Linux server. Everything OralIQ needs
to recover is in that one database: users, exams, submissions, grades, payments, and the
recordings still waiting to be graded. Nothing user-generated lives on the app server's disk, so the
database plus the server's secrets (`SECRET_KEY` and the other settings, kept separately) is
the whole recovery set.

`oraliq_db_backup.py` uses only the Python standard library and the PostgreSQL client tools. It
does not import the app.

## What one backup run does

1. Checks the settings. `BACKUP_DIR` must be outside the app folder and outside `/tmp`, and must
   not be readable by other users.
2. Takes a lock, so two runs never overlap.
3. Connects with `psql` and compares versions. `pg_dump` must be the server's major version or
   newer.
4. Runs `pg_dump --format=custom` on `BACKUP_SCHEMAS` and gzips the output as it streams to
   `<name>.partial`.
5. Verifies the file:
   - decompresses all of it, so the gzip CRC checks every byte;
   - checks the `PGDMP` header;
   - has `pg_restore --list` read the archive's table of contents;
   - requires at least `BACKUP_MIN_TABLES` tables.
6. Optionally encrypts the file with `gpg` for `BACKUP_GPG_RECIPIENT`. Only the public key is on
   the server, and no plaintext copy is kept.
7. Writes the SHA-256, renames the file into place, and writes `<file>.sha256` and `<file>.json`
   (date, size, tables, versions, `status: verified`).
8. Runs the off-site copy command, if one is configured.
9. Only after all of that succeeds, deletes verified backups older than `BACKUP_RETENTION_DAYS`
   (default 30), always keeping the `BACKUP_MIN_KEEP` (default 7) newest. A failed run never
   deletes anything.

If any step fails, the `.partial` file is removed, the reason is logged with its stage
(`connect`, `pg_dump`, `compress`, `verify`, `encrypt`, `lock`, `config`, `io`), and the alert
command runs.

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | Failed |
| 3 | Verified locally, but not copied off-site |
| 4 | Restore refused |

**Secrets:** the password reaches the client tools through a temporary `.pgpass` file (mode
600, deleted afterwards). It never appears in arguments or in `PGPASSWORD`. Every log line,
including the tools' own error messages, is redacted.

## Install on the server (once)

```sh
sudo apt install postgresql-client-16 gnupg      # match the server's major version
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin oraliq-backup
sudo install -d -m 700 -o oraliq-backup -g oraliq-backup /var/backups/oraliq
sudo install -d -m 755 /opt/oraliq/ops/backup /etc/oraliq
sudo install -m 755 oraliq_db_backup.py alert_on_failure.sh /opt/oraliq/ops/backup/
sudo install -m 600 -o root -g root backup.env.example /etc/oraliq/backup.env   # then edit it
sudo install -m 644 systemd/oraliq-db-backup.service systemd/oraliq-db-backup.timer \
     systemd/oraliq-db-backup-alert@.service /etc/systemd/system/
# encryption: import ONLY the public key for the backup user
sudo -u oraliq-backup gpg --import oraliq-backup-public.asc
sudo systemctl daemon-reload
sudo systemctl start oraliq-db-backup.service    # first run by hand; check the log
sudo systemctl enable --now oraliq-db-backup.timer
```

- **Logs:** `journalctl -u oraliq-db-backup`, and `BACKUP_LOG_FILE` if it is set.
- **Next run:** `systemctl list-timers oraliq-db-backup.timer`.
- **Change the time:** edit `OnCalendar` in the timer.
- **Without systemd**, use cron. Put this in `/etc/cron.d/oraliq-backup` (the env file must then
  be readable by `oraliq-backup`):
  `30 3 * * * oraliq-backup /bin/sh -c 'set -a; . /etc/oraliq/backup.env; set +a; /usr/bin/python3 /opt/oraliq/ops/backup/oraliq_db_backup.py backup'`

**Alerts:** a failure runs `BACKUP_ALERT_COMMAND` twice. The tool runs it with the failed stage,
and systemd runs it again through `OnFailure=`; the second one also catches a run that crashed
or never started. Point the command at whatever reaches a person: a Telegram or Slack webhook,
mail, or a dead-man's switch such as healthchecks.io. A dead-man's switch also tells you when the
timer stops running at all.

## Restore (always into a database you name)

```sh
oraliq_db_backup.py list
oraliq_db_backup.py verify  oraliq_oraliq_20261102T033012Z.dump.gz.gpg
oraliq_db_backup.py restore oraliq_oraliq_20261102T033012Z.dump.gz.gpg --check-only
RESTORE_DATABASE_URL=postgresql://...@restore-test-host/oraliq_restore_test \
  oraliq_db_backup.py restore oraliq_oraliq_20261102T033012Z.dump.gz.gpg
```

**Checks before anything is touched:**

1. **Checksum.**
2. **Decryption,** which needs the private key on the restore machine.
3. **Full read-back,** as in step 5 of a backup run.

**Safety rules:**

- **The target is the database in the environment variable named by `--target-env`**
  (default `RESTORE_DATABASE_URL`). It is never an argument, and there is no default target.
- **A target that already has tables is refused**, unless both `--replace-existing` and
  `--confirm <its database name>` are given.
- **The database the backups are taken from is refused as a target**, unless
  `--i-am-restoring-production` is also given.

The restore runs in **one transaction** (`--single-transaction --exit-on-error`), so a failure
leaves the target unchanged. Afterwards the tool counts the rows of every table in the archive,
and reports any table that did not arrive (exit 1).

**Restore drill:** restore the latest backup into a scratch database at least once a month, and
check the report. A backup that has never been restored is unproven.

## Off-site copies and encryption (decisions for the owner)

A copy on the same server is lost along with the server, or along with anyone who controls it.
At least one copy must live with **another provider, under credentials the app server cannot use
to delete it**: an append-only bucket, object lock, or a separate account.

| Option | What you get | What it costs |
|---|---|---|
| S3-compatible object storage (Backblaze B2, Cloudflare R2, Wasabi, AWS S3) with object lock / versioning, via `rclone` or `aws s3 cp` in `BACKUP_UPLOAD_COMMAND` | Off-site, immutable copies; cheap for a few GB | An account and a key pair; installing rclone or awscli on the server |
| The managed PostgreSQL provider's own backups (Supabase, Neon, DigitalOcean, RDS) | Daily snapshots, often PITR, no work on the server | Same provider as the live data; limited retention on low tiers; restores usually only inside the provider |
| A second server you control, via `scp`/`rsync` | Simple | It must not be reachable with the app server's credentials |

**Encryption:** encrypt with `gpg` to a key whose **private** half is kept offline (password
manager or hardware key). Then a stolen backup, or a stolen server, does not expose users' data,
biometric templates or payment records.

## pg_dump, provider backups and PITR

| | pg_dump (this tool) | Provider's automatic backups | Point-in-time recovery (PITR) |
|---|---|---|---|
| **What it is** | A logical snapshot of the schemas, once a day | The provider's physical snapshots, usually daily | A base backup plus the continuous WAL stream, so any second inside the window can be restored |
| **Data you can lose** | Up to 24 hours | Up to 24 hours | Seconds to minutes |
| **Restores into** | Any PostgreSQL of the same or a newer major version, any provider | Usually only a new instance at that provider | The same provider/cluster setup |
| **Protects against** | Provider loss, account lockout, bad migrations, deleted rows (you can restore into a side database and copy rows back) | Disk and instance failure | "Somebody ran a bad UPDATE at 14:03" |
| **Limits** | Not continuous. Big databases take long to dump and restore. Needs client tools. | Tied to the provider and its retention. Usually can't be downloaded or verified by you. | Costs extra on most managed tiers. Still the same provider. |

**Recommendation:**
- Use the provider's daily backups **and** PITR for fast, fine-grained recovery.
- Use this tool for an **independent, off-provider, encrypted** daily copy that you have actually
  restored.
- None of them replaces the others.
- A VPS or disk snapshot is **not** a database backup: a snapshot of a running PostgreSQL can be
  inconsistent, and it shares the provider and the account with the server.

## Older scripts

`scripts/backup_db.ps1` and `backend/backup_db.py` are Windows/SQLite-era development helpers, not
production backups (see the Phase 4 report). `backend/fix_db.py` **drops tables**; it now refuses
to run unless it is pointed at a development SQLite database.
