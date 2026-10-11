"""Điểm khởi chạy MCP server cho Claude Code (xem .mcp.json ở gốc repo).

Chạy như một script để thư mục backend/ tự nằm trong sys.path, không phụ thuộc thư mục hiện hành.
"""

from mcp_server.server import main

if __name__ == "__main__":
    main()
