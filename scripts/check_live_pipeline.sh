#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <backend-base-url> <camera-id>"
  echo "Example: $0 http://127.0.0.1:\${BACKEND_PORT:-8000} recam_01"
  echo "Use the exact backend URL printed by your startup script."
  exit 1
fi

BASE_URL="${1%/}"
CAMERA_ID="$2"

echo "Checking backend..."
curl -fsS "$BASE_URL/" | python3 -m json.tool

echo
echo "Checking summary for camera: $CAMERA_ID"
curl -fsS "$BASE_URL/analytics/summary?camera_id=$CAMERA_ID" | python3 -m json.tool

echo
echo "Checking recent events for camera: $CAMERA_ID"
curl -fsS "$BASE_URL/events/recent?camera_id=$CAMERA_ID&limit=5" | python3 -m json.tool

echo
echo "Checking violation breakdown for camera: $CAMERA_ID"
curl -fsS "$BASE_URL/analytics/violations?camera_id=$CAMERA_ID" | python3 -m json.tool
