from mcp.server.fastmcp import FastMCP
from tools.spending import (
    get_spending_summary,
    get_spending_by_category,
    get_recent_transactions,
)

mcp = FastMCP("personalkin")

mcp.tool()(get_spending_summary)
mcp.tool()(get_spending_by_category)
mcp.tool()(get_recent_transactions)

if __name__ == "__main__":
    mcp.run()
