#!/usr/bin/env bash
# Copyright (c) PyPTO Contributors.
# Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
# See LICENSE in the root of the software repository for the full text of the License.
set -euo pipefail

: "${DEVICE:?Set DEVICE to the allocated A6 device ID}"
: "${ASCEND_HOME_PATH:?Load the A6 CANN environment}"
swa=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$swa/../../.."
python -m pip install -r tests/fdwic/dsv41_scheduler/production/requirements-bound.txt
SWA_SYNC_BOUND=1 exec bash "$swa/test_a6_swa.sh" "$DEVICE"
