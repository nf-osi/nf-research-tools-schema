#!/bin/bash
# Run improved mining with progress tracking

LOG_FILE="tool_coverage/outputs/improved_mining.log"
OUTPUT_FILE="tool_coverage/outputs/processed_publications_improved.csv"

echo "Starting improved mining at $(date)"
echo "Log: $LOG_FILE"
echo "Output: $OUTPUT_FILE"
echo ""

# Run the improved mining
python tool_coverage/scripts/mine_publications_improved.py > "$LOG_FILE" 2>&1

EXIT_CODE=$?

echo ""
echo "Completed at $(date) with exit code $EXIT_CODE"

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✅ Mining completed successfully!"
    echo ""
    echo "Results:"
    if [ -f "$OUTPUT_FILE" ]; then
        LINES=$(wc -l < "$OUTPUT_FILE")
        SIZE=$(ls -lh "$OUTPUT_FILE" | awk '{print $5}')
        echo "  - Publications with tools: $((LINES - 1))"
        echo "  - File size: $SIZE"
        echo "  - Location: $OUTPUT_FILE"
    fi

    # Show summary from log
    echo ""
    echo "Summary:"
    tail -20 "$LOG_FILE" | grep -A 10 "SUMMARY" || echo "  (See $LOG_FILE for details)"
else
    echo ""
    echo "❌ Mining failed with exit code $EXIT_CODE"
    echo "  Check $LOG_FILE for errors"
    tail -50 "$LOG_FILE" | grep -B 5 -A 5 "Error"
fi
