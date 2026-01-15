#!/usr/bin/env bash
CURRENT_FILE_DIR=$(dirname "$0")
REPORTS_DIRECTORY=$CURRENT_FILE_DIR/../../reports
set -euo pipefail

trap 'echo "⛔ Ctrl+C pressed. Exiting..."; exit 130' INT

while read -r diff_file; do
    echo "$diff_file"
    dir_path=$(dirname "$diff_file")
    dir_name=$(basename "$dir_path")
    
    # Extract agent_id from the path
    # Path format: .../reports/agent_id/detection_name/final-sound.diff
    agent_dir=$(dirname "$dir_path")
    agent_id=$(basename "$agent_dir")
    
    uv run python scripts/eval/run_tests.py "$diff_file" \
        --detection-name "$dir_name" < /dev/null  &> ${diff_file}.log || \
        uv run python "$CURRENT_FILE_DIR/change_result.py" "$REPORTS_DIRECTORY/$agent_id.json" "$dir_name" "internal_tests_failure"
done < <(find "$REPORTS_DIRECTORY" -type f -name "final-sound.diff")