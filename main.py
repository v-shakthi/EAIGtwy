"""
main.py — Start the Enterprise AI Gateway server.

Usage:
    python main.py                  # Start gateway on port 8000
    python main.py --port 9000      # Custom port
    python main.py --reload         # Dev mode with hot reload
"""

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Enterprise AI Gateway")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Enable hot reload (dev mode)")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════╗
║         Enterprise AI Gateway v1.0.0            ║
║   Multi-Provider · PII Redaction · Budget Mgmt  ║
╠══════════════════════════════════════════════════╣
║  API:       http://localhost:{args.port}             ║
║  Docs:      http://localhost:{args.port}/docs        ║
║  Dashboard: streamlit run dashboard/app.py       ║
╚══════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "gateway.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
