#!/bin/sh
set -e

# Generate /usr/share/nginx/html/apps/registry.json from $APPS env var.
# APPS is a comma-separated list, e.g. "exam-corrector,attendance-checker"
if [ -n "$APPS" ]; then
    APPS_JSON=$(
        echo "$APPS" \
        | tr ',' '\n' \
        | sed '/^[[:space:]]*$/d' \
        | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
        | sed 's/.*/"&"/' \
        | tr '\n' ',' \
        | sed 's/,$//'
    )
    echo "{\"apps\":[$APPS_JSON]}" > /usr/share/nginx/html/apps/registry.json
fi

exec nginx -g 'daemon off;'
