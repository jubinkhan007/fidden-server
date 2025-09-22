#!/bin/sh
# wait-for-redis.sh
set -e

host="$1"
shift
cmd="$@"

until nc -z "$host" 6379; do
  echo "Waiting for Redis at $host:6379..."
  sleep 1
done

echo "Redis is up - executing command"
exec $cmd