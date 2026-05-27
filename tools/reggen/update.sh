#!/usr/bin/env bash
# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
#
# Script to cleanly vendor third-party tools using native Git sparse-checkout.

set -e

TARGET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_FILE="$TARGET_DIR/tools.yml"

if [ ! -f "$VENDOR_FILE" ]; then
    echo "[ERROR] $VENDOR_FILE not found!"
    exit 1
fi

echo "[*] Reading upstream info from tools.yml..."
REPO_URL=$(awk -F'"' '/^[[:space:]]*url:/ {print $2}' "$VENDOR_FILE")
REVISION=$(awk -F'"' '/^[[:space:]]*revision:/ {print $2}' "$VENDOR_FILE")

if [ -z "$REPO_URL" ] || [ -z "$REVISION" ]; then
    echo "[ERROR] Could not parse url or revision from $VENDOR_FILE"
    exit 1
fi

echo "  -> URL: $REPO_URL"
echo "  -> Revision: $REVISION"

echo "[*] Parsing mapped files from tools.yml..."
MAPPINGS=$(awk -F'"' '
  $1 ~ /^[[:space:]]*- from:/ { from_val = $2 }
  $1 ~ /^[[:space:]]*to:/ { to_val = $2; print from_val "|" to_val }
' "$VENDOR_FILE")

if [ -z "$MAPPINGS" ]; then
    echo "[ERROR] No mapped_files found in $VENDOR_FILE"
    exit 1
fi

FROM_PATHS=""
for mapping in $MAPPINGS; do
    FROM_PATHS="$FROM_PATHS ${mapping%|*}"
done

TEMP_DIR=$(mktemp -d)

echo "[*] Cloning repository (metadata only, skipping blobs)..."
# --filter=blob:none downloads only the tree structure, making it extremely fast
git clone --filter=blob:none --no-checkout "$REPO_URL" "$TEMP_DIR"

pushd "$TEMP_DIR" > /dev/null

echo "[*] Configuring Git sparse-checkout for:$FROM_PATHS"
git sparse-checkout set $FROM_PATHS

echo "[*] Checking out revision: $REVISION..."
git checkout "$REVISION"

popd > /dev/null

echo "[*] Copying files to $TARGET_DIR..."
for mapping in $MAPPINGS; do
    FROM_PATH="${mapping%|*}"
    TO_PATH="${mapping#*|}"
    
    echo "  -> Copying $FROM_PATH to $TO_PATH"
    if [[ "$FROM_PATH" == */ ]]; then
        mkdir -p "$TARGET_DIR/$TO_PATH"
        cp -r "$TEMP_DIR/$FROM_PATH"* "$TARGET_DIR/$TO_PATH"
    else
        mkdir -p "$(dirname "$TARGET_DIR/$TO_PATH")"
        cp "$TEMP_DIR/$FROM_PATH" "$TARGET_DIR/$TO_PATH"
    fi
done

echo "[*] Cleaning up temporary files..."
rm -rf "$TEMP_DIR"

echo "[SUCCESS] Vendoring complete!"
