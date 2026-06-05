#!/bin/bash
# Launch FamilySearch User Segmentation Dashboard
# Usage:
#   ./run_dashboard.sh        # Dashboard v2 (default)
#   ./run_dashboard.sh v1     # Phase 0 dashboard (original)

cd "$(dirname "$0")"

VERSION="${1:-v2}"
if [ "$VERSION" = "v1" ]; then
    echo "Launching Phase 0 dashboard..."
    .venv/bin/streamlit run dashboard/app.py --server.port 8501 --server.headless true
else
    echo "Launching Dashboard v2..."
    .venv/bin/streamlit run dashboard_v2/Home.py --server.port 8501 --server.headless true --server.runOnSave true
fi
