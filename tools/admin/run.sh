#!/bin/bash
# Start both Jekyll dev server and the blog admin tool.
# Usage: ./tools/admin/run.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BLOG_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Jekyll Blog Admin ==="
echo "Blog root: $BLOG_ROOT"
echo ""

# Check Python dependencies
if ! python3 -c "import flask" 2>/dev/null; then
    echo "Installing Python dependencies..."
    pip3 install -r "$SCRIPT_DIR/requirements.txt"
fi

# Create _drafts directory if needed
mkdir -p "$BLOG_ROOT/_drafts"

# Start Jekyll in background
echo "Starting Jekyll on http://localhost:4000 ..."
cd "$BLOG_ROOT" && bundle exec jekyll serve --port 4000 --livereload &
JEKYLL_PID=$!

# Start admin tool
echo "Starting Admin on http://127.0.0.1:5001 ..."
cd "$SCRIPT_DIR" && python3 app.py &
ADMIN_PID=$!

sleep 2
echo ""
echo "=== Both servers running ==="
echo "  Blog:  http://localhost:4000"
echo "  Admin: http://127.0.0.1:5001"
echo ""
echo "Press Ctrl+C to stop both servers"

# Clean shutdown
trap "echo ''; echo 'Shutting down...'; kill $JEKYLL_PID $ADMIN_PID 2>/dev/null; exit 0" INT TERM

wait
