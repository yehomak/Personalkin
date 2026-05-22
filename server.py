from mcp.server.fastmcp import FastMCP
from tools.spending import (
    get_spending_summary,
    get_spending_by_category,
    get_recent_transactions,
    get_transactions_in_range,
)
from tools.calendar import get_upcoming_events, get_events_on_date
from tools.garmin import (
    get_health_snapshot,
    get_sleep_trend,
    get_hrv_trend,
    get_body_battery_trend,
    get_training_load,
    get_health_on_date,
    get_health_in_range,
)

mcp = FastMCP("personalkin")

mcp.tool()(get_spending_summary)
mcp.tool()(get_spending_by_category)
mcp.tool()(get_recent_transactions)
mcp.tool()(get_transactions_in_range)
mcp.tool()(get_upcoming_events)
mcp.tool()(get_events_on_date)
mcp.tool()(get_health_snapshot)
mcp.tool()(get_sleep_trend)
mcp.tool()(get_hrv_trend)
mcp.tool()(get_body_battery_trend)
mcp.tool()(get_training_load)
mcp.tool()(get_health_on_date)
mcp.tool()(get_health_in_range)

if __name__ == "__main__":
    mcp.run()
