#!/usr/bin/env python3
"""
Simple HTTP server to serve the comparison viewer HTML file.

view_comparison.html handles both equivalence comparisons and prefetch
comparisons (from run_comparison.py). It auto-detects prefetch/seek data
in the loaded JSON and shows seek markers and prefetch info when present.
"""

import http.server
import socketserver
import webbrowser
import os
from pathlib import Path

PORT = 8000


class ComparisonHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()


def main():
    script_dir = Path(__file__).parent
    os.chdir(script_dir)

    Handler = ComparisonHTTPRequestHandler

    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Server running at http://localhost:{PORT}/")
        print(f"Open http://localhost:{PORT}/view_comparison.html in your browser")
        print("Press Ctrl+C to stop the server")

        try:
            webbrowser.open(f'http://localhost:{PORT}/view_comparison.html')
        except Exception:
            pass

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")


if __name__ == '__main__':
    main()

