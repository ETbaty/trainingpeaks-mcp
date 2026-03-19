"""Tests for athlete settings tools."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.settings import (
    _parse_pace_to_ms,
    tp_get_athlete_settings,
    tp_update_ftp,
    tp_update_hr_zones,
    tp_update_nutrition,
    tp_update_speed_zones,
)


class TestGetAthleteSettings:
    @pytest.mark.asyncio
    async def test_success(self):
        response = APIResponse(success=True, data={"threshold": 280, "zones": []})
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_athlete_settings()
        assert "settings" in result


class TestUpdateFTP:
    @pytest.mark.asyncio
    async def test_coggan_zones_320w(self):
        """FTP 320W should produce correct Coggan zone boundaries."""
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.put = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_ftp(ftp=320)

        assert result["success"] is True
        assert result["ftp"] == 320
        zones = result["zones"]
        assert len(zones) == 5
        # Z1: 0-55% of 320 = 0-176
        assert zones[0]["minimum"] == 0
        assert zones[0]["maximum"] == 176
        # Z2: 56-75% = 179-240
        assert zones[1]["minimum"] == 179
        assert zones[1]["maximum"] == 240
        # Z4: 91-105% = 291-336
        assert zones[3]["minimum"] == 291
        assert zones[3]["maximum"] == 336

    @pytest.mark.asyncio
    async def test_ftp_validation(self):
        result = await tp_update_ftp(ftp=0)
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"


class TestUpdateHRZones:
    @pytest.mark.asyncio
    async def test_threshold_update(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.put = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_hr_zones(threshold_hr=165)

        assert result["success"] is True
        payload = mock_instance.put.call_args[1]["json"]
        assert payload["threshold"] == 165

    @pytest.mark.asyncio
    async def test_max_hr_only(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.put = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_hr_zones(max_hr=195)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_no_params_rejected(self):
        result = await tp_update_hr_zones()
        assert result["isError"] is True


class TestUpdateSpeedZones:
    def test_parse_run_pace(self):
        """4:30/km = 1000m / 270s = 3.704 m/s."""
        speed = _parse_pace_to_ms("4:30/km")
        assert abs(speed - 3.704) < 0.01

    def test_parse_swim_pace(self):
        """1:45/100m = 100m / 105s = 0.952 m/s."""
        speed = _parse_pace_to_ms("1:45/100m", is_swim=True)
        assert abs(speed - 0.952) < 0.01

    @pytest.mark.asyncio
    async def test_run_pace_update(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.put = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_speed_zones(run_threshold_pace="4:30/km")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_invalid_pace_format(self):
        result = await tp_update_speed_zones(run_threshold_pace="invalid")
        assert result["isError"] is True

    @pytest.mark.asyncio
    async def test_no_params_rejected(self):
        result = await tp_update_speed_zones()
        assert result["isError"] is True


class TestUpdateNutrition:
    @pytest.mark.asyncio
    async def test_success(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_nutrition(planned_calories=2500)

        assert result["success"] is True
        assert result["planned_calories"] == 2500
