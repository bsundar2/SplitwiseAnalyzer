#!/bin/bash
# Helper script to run merchant review workflow
# Usage: ./review.sh [command] [options]

set -e

# Set project root and Python path
PROJECT_ROOT="/home/balaji94/PycharmProjects/SplitwiseImporter"
export PYTHONPATH="$PROJECT_ROOT"

# Activate virtual environment
source "$PROJECT_ROOT/.venv/bin/activate"

# Function to display usage
usage() {
    echo "Usage: ./review.sh [command] [options]"
    echo ""
    echo "Commands:"
    echo "  preview [N]        - Show N sample merchants (default: 10)"
    echo "  start [--batch N]  - Start reviewing merchants (optionally in batches)"
    echo "  continue N         - Continue from transaction N"
    echo "  stats              - Show review statistics"
    echo "  apply [--dry-run]  - Apply corrections to config"
    echo "  help               - Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./review.sh preview 5           # Preview 5 merchants"
    echo "  ./review.sh start --batch 20    # Review 20 merchants"
    echo "  ./review.sh continue 50         # Continue from transaction 50"
    echo "  ./review.sh stats               # Check progress"
    echo "  ./review.sh apply --dry-run     # Preview changes"
    echo "  ./review.sh apply               # Apply changes"
    exit 0
}

# Parse command
COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
    preview)
        N="${1:-10}"
        echo "👀 Previewing merchants..."
        python "$PROJECT_ROOT/src/preview_review.py" -n "$N"
        ;;
    
    start)
        echo "🔍 Starting merchant review..."
        python "$PROJECT_ROOT/src/review_merchants.py" "$@"
        ;;
    
    continue)
        START="${1:-0}"
        echo "▶️  Continuing from transaction $START..."
        python "$PROJECT_ROOT/src/review_merchants.py" --start "$START"
        ;;
    
    stats)
        echo "📊 Review statistics:"
        python "$PROJECT_ROOT/src/review_merchants.py" --stats
        ;;
    
    apply)
        echo "✅ Applying feedback..."
        python "$PROJECT_ROOT/src/apply_review_feedback.py" "$@"
        ;;
    
    help|--help|-h)
        usage
        ;;
    
    *)
        echo "❌ Unknown command: $COMMAND"
        echo ""
        usage
        ;;
esac
