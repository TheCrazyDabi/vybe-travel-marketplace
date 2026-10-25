import os
import sys

# Ensure project root is on the path so modules are found in Vercel's serverless environment
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app

# Vercel looks for 'app' or callable WSGI application
app = create_app()
