#!/usr/bin/env bash
set -euo pipefail

BROKER_HOST=""
BROKER_PORT="1883"
OUT_DIR="artifacts/recamera_phase0"

usage() {
  echo "Usage: $0 --broker-host <HOST> [--broker-port <PORT>] [--out-dir <DIR>]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --broker-host)
      BROKER_HOST="$2"
      shift 2
      ;;
    --broker-port)
      BROKER_PORT="$2"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$BROKER_HOST" ]]; then
  echo "Error: --broker-host is required"
  usage
  exit 1
fi

mkdir -p "$OUT_DIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
SYS_OUT="$OUT_DIR/system_${STAMP}.txt"
NET_OUT="$OUT_DIR/network_${STAMP}.txt"
PY_OUT="$OUT_DIR/python_${STAMP}.txt"

{
  echo "timestamp=$(date -Is)"
  echo "hostname=$(hostname)"
  echo "kernel=$(uname -a)"
  echo "uptime=$(uptime || true)"
  echo
  echo "==== cpu info ===="
  cat /proc/cpuinfo 2>/dev/null || sysctl -a 2>/dev/null | grep -Ei 'machdep.cpu|hw.physicalcpu|hw.logicalcpu' || true
  echo
  echo "==== memory info ===="
  free -h 2>/dev/null || vm_stat 2>/dev/null || true
  echo
  echo "==== disk info ===="
  df -h
} > "$SYS_OUT"

{
  echo "timestamp=$(date -Is)"
  echo "broker_host=$BROKER_HOST"
  echo "broker_port=$BROKER_PORT"
  echo
  echo "==== ping ===="
  ping -c 3 "$BROKER_HOST" || true
  echo
  echo "==== tcp port test ===="
  nc -zv "$BROKER_HOST" "$BROKER_PORT" || true
} > "$NET_OUT" 2>&1

{
  echo "timestamp=$(date -Is)"
  echo "==== python version ===="
  python3 --version || true
  echo
  echo "==== pip list (top section) ===="
  python3 -m pip list 2>/dev/null | head -n 80 || true
  echo
  echo "==== import checks ===="
  python3 - <<'PY'
mods = ["cv2", "numpy", "scipy", "paho.mqtt.client", "ultralytics", "yaml"]
for m in mods:
    try:
        __import__(m)
        print(f"OK import {m}")
    except Exception as e:
        print(f"FAIL import {m}: {e}")
PY
} > "$PY_OUT" 2>&1

echo "Wrote: $SYS_OUT"
echo "Wrote: $NET_OUT"
echo "Wrote: $PY_OUT"
echo "Runtime probe complete"
