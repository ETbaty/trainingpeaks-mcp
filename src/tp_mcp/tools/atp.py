"""Annual Training Plan tool."""

import logging
from typing import Any

from pydantic import ValidationError

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import DateRangeInput, format_validation_error

logger = logging.getLogger("tp-mcp")


async def tp_get_atp(start_date: str, end_date: str) -> dict[str, Any]:
    """Get Annual Training Plan - weekly TSS targets, training periods, races.

    Args:
        start_date: Start date in ISO format (YYYY-MM-DD).
        end_date: End date in ISO format (YYYY-MM-DD).

    Returns:
        Dict with weekly ATP data.
    """
    try:
        params = DateRangeInput(start_date=start_date, end_date=end_date)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        start_str = params.start_date.isoformat()
        end_str = params.end_date.isoformat()
        endpoint = f"/fitness/v1/athletes/{athlete_id}/atp/{start_str}/{end_str}"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data:
            return {
                "weeks": [],
                "count": 0,
                "message": "No ATP data for this date range.",
            }

        data = response.data if isinstance(response.data, list) else []
        weeks = [
            {
                "week": w.get("week", ""),
                "volume": w.get("volume", 0),
                "period": w.get("period", ""),
                "race_name": w.get("raceName", ""),
                "race_priority": w.get("racePriority", ""),
                "weeks_to_event": w.get("weeksToNextPriorityEvent", 0),
            }
            for w in data
        ]

        return {
            "weeks": weeks,
            "count": len(weeks),
            "date_range": {"start": start_date, "end": end_date},
        }
