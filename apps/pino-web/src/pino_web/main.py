from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from pino_web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Pino web API.")
    parser.add_argument("--config", default=None, help="Path to a Pino config file.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", default=8765, type=int, help="Port to bind.")
    args = parser.parse_args()
    app = create_app(config_path=None if args.config is None else Path(args.config))
    uvicorn.run(app, host=args.host, port=args.port, reload=False)
