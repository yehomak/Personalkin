from mcp.server.fastmcp import FastMCP
from tools.spending import (
    get_spending_summary,
    get_spending_by_category,
    get_recent_transactions,
)
from tools.calendar import get_upcoming_events, get_events_on_date

mcp = FastMCP("personalkin")

mcp.tool()(get_spending_summary)
mcp.tool()(get_spending_by_category)
mcp.tool()(get_recent_transactions)
mcp.tool()(get_upcoming_events)
mcp.tool()(get_events_on_date)

if __name__ == "__main__":
    mcp.run()
