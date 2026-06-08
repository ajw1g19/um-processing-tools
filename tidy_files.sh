#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
RUN_DIR="run"

usage() {
  echo "Usage: $0 [-n|--dry-run] [run_dir]"
  echo "  -n, --dry-run   Show what would be deleted, but do not delete"
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    -n|--dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      RUN_DIR="$1"
      shift
      ;;
  esac
done

if [ ! -d "$RUN_DIR" ]; then
  echo "Directory not found: $RUN_DIR"
  exit 1
fi

count=0

while IFS= read -r -d '' file; do
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "Would delete: $file"
  else
    rm -f -- "$file"
    echo "Deleted: $file"
  fi
  count=$((count + 1))
done < <(find "$RUN_DIR" -mindepth 2 -type f -print0)

if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry-run complete. Files that would be deleted: $count"
else
  echo "Total files deleted: $count"
fi