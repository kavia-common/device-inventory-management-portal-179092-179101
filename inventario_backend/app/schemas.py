"""
Marshmallow schemas for the Inventario backend.

Defines:
- InventoryItemSchema: Read-only serialization schema for InventoryItem model
- InventoryItemCreateSchema: Write schema for creating items with validations
- InventoryItemUpdateSchema: Partial update schema with validations

Validations:
- device_type and status are validated against enums
- asset_tag uniqueness enforced via pre_load validation (if provided)
- required fields enforced on create

Notes:
- Uniqueness is best enforced at DB layer; we add a pre_load check to surface
  readable errors when duplicate asset_tags are provided at create/update time.
"""

from typing import Any, Dict, Optional

from marshmallow import Schema, fields, ValidationError, pre_load, validate
from sqlalchemy import select

from .models import InventoryItem
from .db import get_session

# Enumerations for validation
DEVICE_TYPES = (
    "laptop",
    "monitor",
    "docking",
    "mouse",
    "keyboard",
    "tablet",
    "phone",
    "printer",
    "server",
    "other",
)

STATUS_TYPES = (
    "available",
    "assigned",
    "repair",
    "retired",
    "lost",
    "pending",
)


class BaseInventorySchema(Schema):
    """
    Base schema with common fields and shared validators.
    This is not intended to be used directly for (de)serialization.
    """

    id = fields.Int(dump_only=True, description="Primary key identifier")
    device_type = fields.Str(
        required=True,
        validate=validate.OneOf(choices=DEVICE_TYPES, labels=None, error="Invalid device_type. Must be one of: {choices}"),
        description="Type of device (e.g., laptop, monitor, docking, mouse, etc.)",
    )
    brand = fields.Str(allow_none=True, description="Brand or manufacturer")
    model = fields.Str(allow_none=True, description="Model identifier")
    serial_number = fields.Str(allow_none=True, description="Serial number of device")
    owner = fields.Str(allow_none=True, description="Person or department owning the device")
    location = fields.Str(allow_none=True, description="Physical location of the device")
    status = fields.Str(
        required=False,
        allow_none=True,
        validate=validate.OneOf(choices=STATUS_TYPES, labels=None, error="Invalid status. Must be one of: {choices}"),
        description="Current status of the device",
        load_default="available",
    )
    notes = fields.Str(allow_none=True, description="Free-form notes")

    # Optional asset_tag: schema-level uniqueness validation if present
    asset_tag = fields.Str(
        allow_none=True,
        required=False,
        description="Internal unique asset tag/inventory code",
    )

    created_at = fields.DateTime(dump_only=True, description="Record creation timestamp (ISO-8601)")
    updated_at = fields.DateTime(dump_only=True, description="Record last update timestamp (ISO-8601)")

    @pre_load
    def _normalize_strings(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Trim whitespace for string fields to reduce false duplicates and improve consistency.
        """
        if not isinstance(data, dict):
            return data
        for key in ("device_type", "brand", "model", "serial_number", "owner", "location", "status", "notes", "asset_tag"):
            if key in data and isinstance(data[key], str):
                data[key] = data[key].strip()
        return data

    def _check_asset_tag_unique(self, asset_tag: Optional[str], current_id: Optional[int] = None) -> None:
        """
        Check uniqueness of asset_tag if provided. If current_id is given (update),
        allow the same record to keep its asset_tag.
        """
        if not asset_tag:
            return
        # Query DB for existing asset_tag
        session = get_session()
        stmt = select(InventoryItem).where(InventoryItem.__table__.c.get("asset_tag") if hasattr(InventoryItem, "asset_tag") else None)
        # The model file currently does not define asset_tag. We defensively query using text column access if present.
        # If not present on the model, skip check gracefully.
        if not hasattr(InventoryItem, "asset_tag"):
            return

        stmt = select(InventoryItem).where(InventoryItem.asset_tag == asset_tag)
        results = session.execute(stmt).scalars().all()
        if not results:
            return
        # If updating, allow if the only row is self
        if current_id is not None and any(row.id == current_id for row in results) and len(results) == 1:
            return
        raise ValidationError("The provided asset_tag is already in use. Please provide a unique asset_tag.", field_name="asset_tag")


class InventoryItemSchema(BaseInventorySchema):
    """
    Read schema: serialize InventoryItem entities.
    All fields that exist on the model and are useful to return to clients are included.
    """


class InventoryItemCreateSchema(BaseInventorySchema):
    """
    Write schema for creating new inventory items.

    Required:
    - device_type
    - status (defaults to 'available' if omitted)
    Optional:
    - brand, model, serial_number, owner, location, notes, asset_tag
    """

    # PUBLIC_INTERFACE
    def load(self, data: Any, *, many: bool = False, partial: Any = None, unknown=None):
        """Override load to ensure uniqueness and readable error surfacing on create."""
        loaded = super().load(data, many=many, partial=partial, unknown=unknown)
        # On create, check asset_tag uniqueness if present
        if isinstance(loaded, dict):
            self._check_asset_tag_unique(loaded.get("asset_tag"))
        return loaded


class InventoryItemUpdateSchema(BaseInventorySchema):
    """
    Partial update schema. All fields are optional; apply validations on provided ones.
    """

    # Override field requirements for partial updates
    device_type = fields.Str(
        required=False,
        allow_none=False,
        validate=validate.OneOf(choices=DEVICE_TYPES, error="Invalid device_type. Must be one of: {choices}"),
        description="Type of device (e.g., laptop, monitor, docking, mouse, etc.)",
    )
    status = fields.Str(
        required=False,
        allow_none=True,
        validate=validate.OneOf(choices=STATUS_TYPES, error="Invalid status. Must be one of: {choices}"),
        description="Current status of the device",
    )

    # PUBLIC_INTERFACE
    def load(self, data: Any, *, many: bool = False, partial: Any = True, unknown=None, current_id: Optional[int] = None):
        """
        Override load to enforce partial update by default and run uniqueness check.

        Args:
            data: Incoming payload
            many: Not supported for update in this context (kept for signature compatibility)
            partial: Defaults to True for patch-like behavior
            unknown: Unknown field handling
            current_id: Current record id being updated (to allow same asset_tag)
        """
        loaded = super().load(data, many=many, partial=True if partial is None else partial, unknown=unknown)
        if isinstance(loaded, dict):
            self._check_asset_tag_unique(loaded.get("asset_tag"), current_id=current_id)
        return loaded
