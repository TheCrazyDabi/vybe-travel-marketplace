import os
import sys
import traceback
import urllib.parse

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from app import app as flask_app

    def app(environ, start_response):
        # 1. Normalize PATH_INFO for Vercel Serverless environment
        qs = environ.get("QUERY_STRING", "")
        if "__path=" in qs:
            params = urllib.parse.parse_qs(qs, keep_blank_values=True)
            if "__path" in params and params["__path"]:
                target_path = params.pop("__path")[0]
                if not target_path.startswith("/"):
                    target_path = "/" + target_path
                environ["PATH_INFO"] = target_path
                clean_pairs = []
                for k, vs in params.items():
                    for v in vs:
                        clean_pairs.append((k, v))
                environ["QUERY_STRING"] = urllib.parse.urlencode(clean_pairs)

        # 2. Check proxy headers if __path was not in query string
        elif environ.get("HTTP_X_VERCEL_PATH"):
            environ["PATH_INFO"] = environ["HTTP_X_VERCEL_PATH"].split("?")[0]
        elif environ.get("HTTP_X_ORIGINAL_URL"):
            environ["PATH_INFO"] = environ["HTTP_X_ORIGINAL_URL"].split("?")[0]
        elif environ.get("HTTP_X_FORWARDED_URI"):
            environ["PATH_INFO"] = environ["HTTP_X_FORWARDED_URI"].split("?")[0]
        else:
            # 3. Strip serverless entrypoint prefixes if still present
            path = environ.get("PATH_INFO", "")
            if path.startswith("/api/index.py"):
                remainder = path[len("/api/index.py"):]
                environ["PATH_INFO"] = remainder if remainder.startswith("/") else ("/" + remainder)
            elif path.startswith("/api/index"):
                remainder = path[len("/api/index"):]
                environ["PATH_INFO"] = remainder if remainder.startswith("/") else ("/" + remainder)

        # Ensure PATH_INFO is never empty
        if not environ.get("PATH_INFO"):
            environ["PATH_INFO"] = "/"

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
