"""Athlete settings tools: zones, FTP, thresholds, nutrition."""

import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import format_validation_error

logger = logging.getLogger("tp-mcp")

# Coggan 5-zone power model boundaries (% of FTP)
COGGAN_ZONES = [
    ("Z1 Active Recovery", 0, 55),
    ("Z2 Endurance", 56, 75),
    ("Z3 Tempo", 76, 90),
    ("Z4 Threshold", 91, 105),
    ("Z5 VO2max", 106, 150),
]


class FTPInput(BaseModel):
    """Validates FTP input."""

    ftp: int = Field(gt=0, le=2000)


class HRZonesInput(BaseModel):
    """Validates HR zones input."""

    threshold_hr: int | None = Field(default=None, gt=50, le=250)
    max_hr: int | None = Field(default=None, gt=50, le=250)
    resting_hr: int | None = Field(default=None, gt=20, le=120)
    workout_type: str = Field(default="general")

    @field_validator("workout_type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in ("general", "bike"):
            raise ValueError("workout_type must be 'general' or 'bike'")
        return v


class SpeedZonesInput(BaseModel):
    """Validates speed zones input."""

    run_threshold_pace: str | None = None
    swim_threshold_pace: str | None = None

    @field_validator("run_threshold_pace", "swim_threshold_pace")
    @classmethod
    def check_pace_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^\d{1,2}:\d{2}(/\w+)?$", v):
            raise ValueError(f"Invalid pace format '{v}'. Use 'M:SS' (e.g. '4:30/km' or '1:45/100m')")
        return v


def _parse_pace_to_ms(pace_str: str, is_swim: bool = False) -> float:
    """Parse a pace string to metres per second.

    Args:
        pace_str: Pace like '4:30/km' or '1:45/100m'.
        is_swim: Whether this is a swim pace (per 100m).

    Returns:
        Speed in metres per second.
    """
    # Strip unit suffix if present
    pace_part = pace_str.split("/")[0]
    parts = pace_part.split(":")
    minutes = int(parts[0])
    seconds = int(parts[1])
    total_seconds = minutes * 60 + seconds

    if total_seconds == 0:
        raise ValueError(f"Invalid pace: {pace_str}")

    if is_swim:
        return 100.0 / total_seconds
    return 1000.0 / total_seconds


async def tp_get_athlete_settings() -> dict[str, Any]:
    """Get athlete settings including FTP, thresholds, zones, and profile.

    Returns:
        Dict with all athlete settings.
    """
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/settings"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data or not isinstance(response.data, dict):
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "No settings data returned.",
            }

        return {"settings": response.data}


async def tp_update_ftp(ftp: int) -> dict[str, Any]:
    """Update FTP and recalculate Coggan 5-zone power model.

    Args:
        ftp: Functional Threshold Power in watts.

    Returns:
        Dict with updated zones or error.
    """
    try:
        params = FTPInput(ftp=ftp)
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

        # Build Coggan zones
        zones = []
        for name, low_pct, high_pct in COGGAN_ZONES:
            zones.append({
                "name": name,
                "minimum": round(params.ftp * low_pct / 100.0),
                "maximum": round(params.ftp * high_pct / 100.0),
            })

        payload = {
            "threshold": params.ftp,
            "zones": zones,
        }

        endpoint = f"/fitness/v2/athletes/{athlete_id}/powerzones"
        response = await client.put(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "ftp": params.ftp,
            "zones": zones,
        }


async def tp_update_hr_zones(
    threshold_hr: int | None = None,
    max_hr: int | None = None,
    resting_hr: int | None = None,
    workout_type: str = "general",
) -> dict[str, Any]:
    """Update heart rate zones.

    Args:
        threshold_hr: Threshold heart rate (optional).
        max_hr: Maximum heart rate (optional).
        resting_hr: Resting heart rate (optional).
        workout_type: 'general' or 'bike' (default 'general').

    Returns:
        Dict with updated zones or error.
    """
    try:
        params = HRZonesInput(
            threshold_hr=threshold_hr,
            max_hr=max_hr,
            resting_hr=resting_hr,
            workout_type=workout_type,
        )
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    if params.threshold_hr is None and params.max_hr is None and params.resting_hr is None:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "At least one of threshold_hr, max_hr, or resting_hr must be provided.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        payload: dict[str, Any] = {}
        if params.threshold_hr is not None:
            payload["threshold"] = params.threshold_hr
        if params.max_hr is not None:
            payload["maximum"] = params.max_hr
        if params.resting_hr is not None:
            payload["resting"] = params.resting_hr

        endpoint = f"/fitness/v2/athletes/{athlete_id}/heartratezones"
        response = await client.put(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "message": "Heart rate zones updated.",
            "updates": payload,
        }


async def tp_update_speed_zones(
    run_threshold_pace: str | None = None,
    swim_threshold_pace: str | None = None,
) -> dict[str, Any]:
    """Update speed/pace zones.

    Args:
        run_threshold_pace: Run threshold pace (e.g. '4:30/km').
        swim_threshold_pace: Swim threshold pace (e.g. '1:45/100m').

    Returns:
        Dict with updated zones or error.
    """
    try:
        params = SpeedZonesInput(
            run_threshold_pace=run_threshold_pace,
            swim_threshold_pace=swim_threshold_pace,
        )
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    if params.run_threshold_pace is None and params.swim_threshold_pace is None:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "At least one of run_threshold_pace or swim_threshold_pace must be provided.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        payload: dict[str, Any] = {}

        if params.run_threshold_pace is not None:
            try:
                speed_ms = _parse_pace_to_ms(params.run_threshold_pace)
                payload["runThreshold"] = speed_ms
            except ValueError as e:
                return {
                    "isError": True,
                    "error_code": "VALIDATION_ERROR",
                    "message": str(e),
                }

        if params.swim_threshold_pace is not None:
            try:
                speed_ms = _parse_pace_to_ms(params.swim_threshold_pace, is_swim=True)
                payload["swimThreshold"] = speed_ms
            except ValueError as e:
                return {
                    "isError": True,
                    "error_code": "VALIDATION_ERROR",
                    "message": str(e),
                }

        endpoint = f"/fitness/v2/athletes/{athlete_id}/speedzones"
        response = await client.put(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "message": "Speed zones updated.",
            "updates": payload,
        }


async def tp_update_nutrition(planned_calories: int) -> dict[str, Any]:
    """Update nutrition settings.

    Args:
        planned_calories: Planned daily calories.

    Returns:
        Dict with confirmation or error.
    """
    if planned_calories < 0 or planned_calories > 20000:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "planned_calories must be between 0 and 20000.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/nutritionsettings"
        payload = {"plannedCalories": planned_calories}
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "planned_calories": planned_calories,
        }


async def tp_get_pool_length_settings() -> dict[str, Any]:
    """Get pool length settings.

    Returns:
        Dict with pool length options and default.
    """
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/poollengthsettings"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {"pool_length_settings": response.data}
