#!/bin/sh
# Railway mounts the volume owned by root. Fix ownership, then run the app as an unprivileged user.
set -eu
chown -R 10001:10001 "${DATA_DIR:-/data}"
exec setpriv --reuid=10001 --regid=10001 --init-groups python -m sequencer serve --no-open
