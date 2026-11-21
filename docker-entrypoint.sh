#!/bin/sh
# Runs before the server inside the container. Two things, both only once.
set -e

# The login cookie is signed with CAMPUS_SECRET. If nobody set one, make a
# long random one on the first start and keep it next to the database, so a
# restart does not log everybody out and the image never runs with the
# placeholder from main.py.
if [ -z "$CAMPUS_SECRET" ]; then
    secret_file="$(dirname "$CAMPUS_DB")/.campus_secret"
    if [ ! -s "$secret_file" ]; then
        python -c "import secrets; print(secrets.token_urlsafe(48))" > "$secret_file"
        chmod 600 "$secret_file"
    fi
    CAMPUS_SECRET="$(cat "$secret_file")"
    export CAMPUS_SECRET
fi

# An empty volume gets the fake students and entries, the same as running
# python -m app.seed by hand. A database that is already there is never
# touched. Set CAMPUS_SEED=0 to start with an empty one instead.
if [ "$CAMPUS_SEED" = "1" ] && [ ! -e "$CAMPUS_DB" ]; then
    python -m app.seed
fi

exec "$@"
