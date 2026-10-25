import os
import sys
import traceback

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from app import app
except Exception as e:
    err_tb = traceback.format_exc()

    def app(environ, start_response):
        status = '500 Internal Server Error'
        headers = [('Content-Type', 'text/html; charset=utf-8')]
        start_response(status, headers)
        html = f"""<!doctype html>
<html>
<head>
    <title>VYBE Initialization Error</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #2B1C19; color: #E5E4E2; padding: 32px; line-height: 1.5; }}
        .card {{ background: #49352F; border: 1px solid rgba(189, 167, 232, 0.38); border-radius: 16px; padding: 24px; max-width: 800px; margin: 0 auto; }}
        h2 {{ color: #FAF9F7; margin-top: 0; }}
        pre {{ background: #180E0E; color: #FFB3A7; padding: 16px; border-radius: 8px; overflow-x: auto; font-size: 13px; border: 1px solid rgba(255, 179, 167, 0.2); }}
    </style>
</head>
<body>
    <div class="card">
        <h2>VYBE Startup Diagnostic</h2>
        <p>The application encountered an initialization issue during serverless cold start:</p>
        <pre>{err_tb}</pre>
    </div>
</body>
</html>"""
        return [html.encode('utf-8')]
