#!/bin/sh

set -e

celery_args="$1"
shift

until celery $celery_args inspect ping; do
  >&2 echo "Celery workers still not available"
  sleep 1
done

>&2 echo "Celery workers are available"
exec "$@"