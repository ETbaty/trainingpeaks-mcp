"""Tests for workout types catalogue tool."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.workout_types import tp_get_workout_types


class TestGetWorkoutTypes:
    @pytest.mark.asyncio
    async def test_returns_hierarchical_structure(self):
        data = [
            {
                "workoutTypeId": 2, "description": "Bike",
                "children": [
                    {"workoutTypeId": 3, "description": "Road Bike"},
                    {"workoutTypeId": 8, "description": "MTB"},
                ],
            },
            {"workoutTypeId": 3, "description": "Run", "children": []},
        ]
        response = APIResponse(success=True, data=data)
        with patch("tp_mcp.tools.workout_types.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workout_types()

        assert result["count"] == 2
        bike_type = result["workout_types"][0]
        assert bike_type["id"] == 2
        assert len(bike_type["subtypes"]) == 2
        assert bike_type["subtypes"][0]["name"] == "Road Bike"

    @pytest.mark.asyncio
    async def test_empty_list(self):
        response = APIResponse(success=True, data=[])
        with patch("tp_mcp.tools.workout_types.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workout_types()

        assert result["count"] == 0
