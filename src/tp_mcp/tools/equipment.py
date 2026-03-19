"""Equipment tools: bikes, shoes, distance tracking."""

import logging
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import format_validation_error

logger = logging.getLogger("tp-mcp")

EQUIPMENT_TYPES = {"bike": 1, "shoe": 2}
BIKE_ONLY_FIELDS = {"wheels", "crank_length_mm"}


class CreateEquipmentInput(BaseModel):
    """Validates input for equipment creation."""

    name: str = Field(min_length=1, max_length=200)
    type: str
    brand: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    date_of_purchase: str | None = None
    starting_distance_km: float | None = Field(default=None, ge=0)
    max_distance_km: float | None = Field(default=None, gt=0)
    is_default: bool = False
    wheels: str | None = None
    crank_length_mm: float | None = Field(default=None, gt=0, le=300)

    @field_validator("type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in EQUIPMENT_TYPES:
            valid = ", ".join(EQUIPMENT_TYPES.keys())
            raise ValueError(f"Invalid type '{v}'. Valid: {valid}")
        return v

    @field_validator("date_of_purchase")
    @classmethod
    def check_date(cls, v: str | None) -> str | None:
        if v is not None:
            date.fromisoformat(v)
        return v


class UpdateEquipmentInput(BaseModel):
    """Validates input for equipment updates."""

    equipment_id: int = Field(gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    brand: str | None = None
    model: str | None = None
    notes: str | None = None
    retired: bool | None = None
    is_default: bool | None = None
    max_distance_km: float | None = Field(default=None, gt=0)
    wheels: str | None = None
    crank_length_mm: float | None = Field(default=None, gt=0, le=300)

    @field_validator("equipment_id", mode="before")
    @classmethod
    def coerce_string(cls, v: object) -> object:
        if isinstance(v, str):
            return int(v)
        return v


async def tp_get_equipment(type: str = "all") -> dict[str, Any]:
    """Get equipment list.

    Args:
        type: Filter by type: 'bike', 'shoe', or 'all' (default 'all').

    Returns:
        Dict with equipment list.
    """
    if type not in ("bike", "shoe", "all"):
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "type must be 'bike', 'shoe', or 'all'.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/equipment"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data or not isinstance(response.data, list):
            return {"equipment": [], "count": 0}

        items = response.data

        # Filter by type
        if type != "all":
            type_id = EQUIPMENT_TYPES[type]
            items = [e for e in items if e.get("equipmentType") == type_id]

        # Format for output
        formatted = []
        for e in items:
            item: dict[str, Any] = {
                "id": e.get("equipmentId"),
                "name": e.get("name"),
                "type": "bike" if e.get("equipmentType") == 1 else "shoe",
                "brand": e.get("brand"),
                "model": e.get("model"),
                "distance_km": round(e.get("distance", 0) / 1000, 1),
                "starting_distance_km": round(e.get("startingDistance", 0) / 1000, 1),
                "max_distance_km": round(e.get("maxDistance", 0) / 1000, 1) if e.get("maxDistance") else None,
                "retired": e.get("retired", False),
                "is_default": e.get("isDefault", False),
                "date_of_purchase": e.get("dateOfPurchase"),
            }
            formatted.append(item)

        return {"equipment": formatted, "count": len(formatted)}


async def tp_create_equipment(
    name: str,
    type: str,
    brand: str | None = None,
    model: str | None = None,
    notes: str | None = None,
    date_of_purchase: str | None = None,
    starting_distance_km: float | None = None,
    max_distance_km: float | None = None,
    is_default: bool = False,
    wheels: str | None = None,
    crank_length_mm: float | None = None,
) -> dict[str, Any]:
    """Create new equipment.

    Args:
        name: Equipment name.
        type: 'bike' or 'shoe'.
        brand: Optional brand name.
        model: Optional model name.
        notes: Optional notes.
        date_of_purchase: Optional purchase date (YYYY-MM-DD).
        starting_distance_km: Optional starting distance in km.
        max_distance_km: Optional maximum distance in km.
        is_default: Whether this is the default equipment.
        wheels: Optional wheel description (bike only).
        crank_length_mm: Optional crank length in mm (bike only).

    Returns:
        Dict with confirmation or error.
    """
    try:
        params = CreateEquipmentInput(
            name=name,
            type=type,
            brand=brand,
            model=model,
            notes=notes,
            date_of_purchase=date_of_purchase,
            starting_distance_km=starting_distance_km,
            max_distance_km=max_distance_km,
            is_default=is_default,
            wheels=wheels,
            crank_length_mm=crank_length_mm,
        )
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    # Reject bike-only fields on shoes
    if params.type == "shoe":
        for field_name in BIKE_ONLY_FIELDS:
            if getattr(params, field_name) is not None:
                return {
                    "isError": True,
                    "error_code": "VALIDATION_ERROR",
                    "message": f"'{field_name}' is only valid for bikes, not shoes.",
                }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        # GET existing equipment array
        endpoint = f"/fitness/v1/athletes/{athlete_id}/equipment"
        get_response = await client.get(endpoint)

        if get_response.is_error:
            return {
                "isError": True,
                "error_code": get_response.error_code.value if get_response.error_code else "API_ERROR",
                "message": get_response.message,
            }

        existing = get_response.data if isinstance(get_response.data, list) else []

        # Build new equipment item
        new_item: dict[str, Any] = {
            "equipmentId": None,
            "name": params.name,
            "equipmentType": EQUIPMENT_TYPES[params.type],
            "brand": params.brand or "",
            "model": params.model or "",
            "notes": params.notes or "",
            "isDefault": params.is_default,
            "retired": False,
            "distance": 0,
            "startingDistance": int((params.starting_distance_km or 0) * 1000),
        }

        if params.max_distance_km is not None:
            new_item["maxDistance"] = int(params.max_distance_km * 1000)
        if params.date_of_purchase:
            new_item["dateOfPurchase"] = params.date_of_purchase
        if params.wheels:
            new_item["wheels"] = params.wheels
        if params.crank_length_mm is not None:
            new_item["crankLength"] = params.crank_length_mm

        # Append and PUT full array
        existing.append(new_item)
        put_response = await client.put(endpoint, json=existing)

        if put_response.is_error:
            return {
                "isError": True,
                "error_code": put_response.error_code.value if put_response.error_code else "API_ERROR",
                "message": put_response.message,
            }

        return {
            "success": True,
            "message": f"Equipment '{params.name}' created.",
        }


async def tp_update_equipment(
    equipment_id: str,
    name: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    notes: str | None = None,
    retired: bool | None = None,
    is_default: bool | None = None,
    max_distance_km: float | None = None,
    wheels: str | None = None,
    crank_length_mm: float | None = None,
) -> dict[str, Any]:
    """Update existing equipment.

    Args:
        equipment_id: Equipment ID.
        name: Optional new name.
        brand: Optional new brand.
        model: Optional new model.
        notes: Optional new notes.
        retired: Optional retirement status.
        is_default: Optional default status.
        max_distance_km: Optional max distance in km.
        wheels: Optional wheel description (bike only).
        crank_length_mm: Optional crank length in mm (bike only).

    Returns:
        Dict with confirmation or error.
    """
    try:
        params = UpdateEquipmentInput(
            equipment_id=equipment_id,
            name=name,
            brand=brand,
            model=model,
            notes=notes,
            retired=retired,
            is_default=is_default,
            max_distance_km=max_distance_km,
            wheels=wheels,
            crank_length_mm=crank_length_mm,
        )
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

        # GET existing equipment array
        endpoint = f"/fitness/v1/athletes/{athlete_id}/equipment"
        get_response = await client.get(endpoint)

        if get_response.is_error:
            return {
                "isError": True,
                "error_code": get_response.error_code.value if get_response.error_code else "API_ERROR",
                "message": get_response.message,
            }

        existing = get_response.data if isinstance(get_response.data, list) else []

        # Find and update the target item
        found = False
        for item in existing:
            if item.get("equipmentId") == params.equipment_id:
                found = True

                # Reject bike-only fields on shoes
                is_shoe = item.get("equipmentType") == 2
                if is_shoe:
                    for field_name in BIKE_ONLY_FIELDS:
                        if getattr(params, field_name) is not None:
                            return {
                                "isError": True,
                                "error_code": "VALIDATION_ERROR",
                                "message": f"'{field_name}' is only valid for bikes, not shoes.",
                            }

                if params.name is not None:
                    item["name"] = params.name
                if params.brand is not None:
                    item["brand"] = params.brand
                if params.model is not None:
                    item["model"] = params.model
                if params.notes is not None:
                    item["notes"] = params.notes
                if params.retired is not None:
                    item["retired"] = params.retired
                    if params.retired and not item.get("retiredDate"):
                        item["retiredDate"] = datetime.now().isoformat()
                if params.is_default is not None:
                    item["isDefault"] = params.is_default
                if params.max_distance_km is not None:
                    item["maxDistance"] = int(params.max_distance_km * 1000)
                if params.wheels is not None:
                    item["wheels"] = params.wheels
                if params.crank_length_mm is not None:
                    item["crankLength"] = params.crank_length_mm
                break

        if not found:
            return {
                "isError": True,
                "error_code": "NOT_FOUND",
                "message": f"Equipment {params.equipment_id} not found.",
            }

        # PUT full array back
        put_response = await client.put(endpoint, json=existing)

        if put_response.is_error:
            return {
                "isError": True,
                "error_code": put_response.error_code.value if put_response.error_code else "API_ERROR",
                "message": put_response.message,
            }

        return {
            "success": True,
            "message": f"Equipment {params.equipment_id} updated.",
        }


async def tp_delete_equipment(equipment_id: str) -> dict[str, Any]:
    """Delete equipment.

    Args:
        equipment_id: Equipment ID.

    Returns:
        Dict with confirmation or error.
    """
    try:
        eid = int(equipment_id)
        if eid <= 0:
            raise ValueError("equipment_id must be positive")
    except (ValueError, TypeError) as e:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": str(e),
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        # GET existing equipment array
        endpoint = f"/fitness/v1/athletes/{athlete_id}/equipment"
        get_response = await client.get(endpoint)

        if get_response.is_error:
            return {
                "isError": True,
                "error_code": get_response.error_code.value if get_response.error_code else "API_ERROR",
                "message": get_response.message,
            }

        existing = get_response.data if isinstance(get_response.data, list) else []

        # Filter out the target item
        remaining = [e for e in existing if e.get("equipmentId") != eid]

        if len(remaining) == len(existing):
            return {
                "isError": True,
                "error_code": "NOT_FOUND",
                "message": f"Equipment {eid} not found.",
            }

        # PUT remaining array back
        put_response = await client.put(endpoint, json=remaining)

        if put_response.is_error:
            return {
                "isError": True,
                "error_code": put_response.error_code.value if put_response.error_code else "API_ERROR",
                "message": put_response.message,
            }

        return {
            "success": True,
            "message": f"Equipment {eid} deleted.",
        }
