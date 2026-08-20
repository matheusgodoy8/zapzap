#!/usr/bin/env bash
set -euo pipefail

PACKAGING="${1:?usage: build-info.sh <packaging-name> [release-tag]}"
RELEASE_TAG="${2:-}"

if [[ -n "${RELEASE_TAG}" && "${RELEASE_TAG}" != "continuous" && ! "${RELEASE_TAG}" =~ ^[vV]?[0-9]+(\.[0-9]+)*(-rc\.[0-9]+)?$ ]]; then
    echo "Invalid release tag: ${RELEASE_TAG}" >&2
    exit 1
fi

cat > zapzap/BuildInfo.py <<EOF_BUILD_INFO
BUILD_CHANNEL = "Official"
BUILD_PROVIDER = "GitHub Actions"
BUILD_REPOSITORY = "${GITHUB_REPOSITORY:-unknown}"
BUILD_PACKAGING = "${PACKAGING}"
BUILD_COMMIT = "${GITHUB_SHA:-unknown}"
BUILD_RELEASE_TAG = "${RELEASE_TAG}"
EOF_BUILD_INFO
