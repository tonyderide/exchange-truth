FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY exchange_truth ./exchange_truth
RUN pip install --no-cache-dir "ccxt" "mcp>=2"
# Read-only key via env: ET_API_KEY / ET_API_SECRET. Starts the MCP server on stdio.
ENTRYPOINT ["python", "-m", "exchange_truth.mcp_server"]
