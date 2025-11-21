#!/bin/bash
# Startup script for Railway/Render deployment

# Create output directory if it doesn't exist
mkdir -p webapp/output

# Start gunicorn with production settings
# Note: db.create_all() and cleanup_old_files() run automatically on import
exec gunicorn -w 4 -b 0.0.0.0:${PORT:-5000} --timeout 120 --access-logfile - --error-logfile - webapp.app:app
