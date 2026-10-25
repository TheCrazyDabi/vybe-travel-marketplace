import os
import sys
import traceback
import json

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from app import app as flask_app

    def app(environ, start_response):
        # 1. Reset SCRIPT_NAME: Vercel sets SCRIPT_NAME to /api/index which forces Flask into 404
        environ["SCRIPT_NAME"] = ""

        # 2. Normalize PATH_INFO to clean root paths
        path = environ.get("PATH_INFO", "")
        if path.startswith("/api/index.py"):
            remainder = path[len("/api/index.py"):]
            environ["PATH_INFO"] = remainder if remainder.startswith("/") else ("/" + remainder)
        elif path.startswith("/api/index"):
            remainder = path[len("/api/index"):]
            environ["PATH_INFO"] = remainder if remainder.startswith("/") else ("/" + remainder)
        elif not path:
            environ["PATH_INFO"] = "/"

        if not environ["PATH_INFO"]:
            environ["PATH_INFO"] = "/"

        # 3. Diagnostic endpoint: /__diag
        if environ.get("PATH_INFO") == "/__diag":
            status = '200 OK'
            headers = [('Content-Type', 'application/json')]
            start_response(status, headers)
            info = {
                "status": "healthy",
                "database_configured": bool(os.environ.get("DATABASE_URL")),
                "serverless": bool(os.environ.get("VERCEL")),
                "env": os.environ.get("FLASK_ENV", "development"),
            }
            return [json.dumps(info, indent=2).encode('utf-8')]

        return flask_app(environ, start_response)

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
