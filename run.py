#!/usr/bin/env python
"""Dev entry point."""
import os

from src.app.create import create_app

app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, port=port)
