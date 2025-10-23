from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..db import session_scope
from ..models import InventoryItem
from ..schemas import (
    InventoryItemCreateSchema,
    InventoryItemSchema,
    InventoryItemUpdateSchema,
    DEVICE_TYPES,
    STATUS_TYPES,
)

# Blueprint definition with OpenAPI tags/description
blp = Blueprint(
    "Items",
    "items",
    url_prefix="/items",
    description="CRUD endpoints for inventory items with pagination, filtering, and sorting.",
)


class PaginationQuerySchema(Schema):
    """Query arguments for pagination, sorting and filtering."""
    page = fields.Int(load_default=1, description="Page number (1-based).")
    page_size = fields.Int(load_default=20, description="Items per page (max 200).")
    sort_by = fields.Str(
        load_default="created_at",
        description="Field to sort by (id, device_type, brand, model, serial_number, owner, location, status, created_at, updated_at).",
    )
    sort_order = fields.Str(
        load_default="desc",
        description="Sort order: asc or desc.",
    )
    # Text search across several fields
    search = fields.Str(load_default=None, allow_none=True, description="Free text search across asset_tag, brand, model, serial_number.")
    # Structured filters
    type = fields.Str(load_default=None, allow_none=True, description="Filter by device_type.")
    status = fields.Str(load_default=None, allow_none=True, description="Filter by status.")
    assigned_to = fields.Str(load_default=None, allow_none=True, description="Filter by owner/assignee.")


class PaginationMetaSchema(Schema):
    """Metadata for paginated responses."""
    total = fields.Int(required=True)
    total_pages = fields.Int(required=True)
    first_page = fields.Int(required=True)
    last_page = fields.Int(required=True)
    page = fields.Int(required=True)
    previous_page = fields.Int(allow_none=True)
    next_page = fields.Int(allow_none=True)


class PaginatedItemsResponseSchema(Schema):
    """Paginated response schema for list endpoint."""
    data = fields.List(fields.Nested(InventoryItemSchema), required=True)
    meta = fields.Nested(PaginationMetaSchema, required=True)


def _safe_page_params(page: int, page_size: int) -> Tuple[int, int]:
    """Clamp and normalize pagination params."""
    if page is None or page < 1:
        page = 1
    if page_size is None or page_size < 1:
        page_size = 20
    if page_size > 200:
        page_size = 200
    return page, page_size


def _apply_filters(query, search: Optional[str], device_type: Optional[str], status: Optional[str], assigned_to: Optional[str]):
    """Apply filtering and search to the query."""
    # Text search across multiple fields if provided
    if search:
        # Not all fields may exist on the model (asset_tag isn't in model). Handle gracefully.
        terms = f"%{search}%"
        conditions = [
            InventoryItem.brand.ilike(terms),
            InventoryItem.model.ilike(terms),
            InventoryItem.serial_number.ilike(terms),
        ]
        # If model later adds asset_tag, include it
        if hasattr(InventoryItem, "asset_tag"):
            conditions.append(getattr(InventoryItem, "asset_tag").ilike(terms))  # type: ignore[attr-defined]
        query = query.where(or_(*conditions))

    if device_type:
        query = query.where(InventoryItem.device_type == device_type)
    if status:
        query = query.where(InventoryItem.status == status)
    if assigned_to:
        # 'assigned_to' maps to 'owner' field in model
        query = query.where(InventoryItem.owner == assigned_to)
    return query


def _apply_sorting(query, sort_by: str, sort_order: str):
    """Apply sorting based on allowed columns."""
    allowed_fields = {
        "id": InventoryItem.id,
        "device_type": InventoryItem.device_type,
        "brand": InventoryItem.brand,
        "model": InventoryItem.model,
        "serial_number": InventoryItem.serial_number,
        "owner": InventoryItem.owner,
        "location": InventoryItem.location,
        "status": InventoryItem.status,
        "created_at": InventoryItem.created_at,
        "updated_at": InventoryItem.updated_at,
    }
    sort_col = allowed_fields.get(sort_by, InventoryItem.created_at)
    direction = desc if (sort_order or "desc").lower() == "desc" else asc
    return query.order_by(direction(sort_col))


def _build_pagination_meta(total: int, page: int, page_size: int) -> Dict[str, Any]:
    """Construct pagination metadata object."""
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    prev_page = page - 1 if page > 1 else None
    next_page = page + 1 if page < total_pages else None
    return {
        "total": total,
        "total_pages": total_pages,
        "first_page": 1,
        "last_page": total_pages,
        "page": page,
        "previous_page": prev_page,
        "next_page": next_page,
    }


@blp.route("/")
class ItemsListResource(MethodView):
    """List and create inventory items."""

    @blp.arguments(PaginationQuerySchema, location="query")
    @blp.response(200, PaginatedItemsResponseSchema)
    @blp.doc(summary="List inventory items", description="Returns a paginated list of items with filtering, search, and sorting.")
    def get(self, args: Dict[str, Any]):
        """
        List inventory items with pagination, filtering, and sorting.

        Query Parameters:
            page: Page number (1-based)
            page_size: Items per page
            sort_by: Column to sort by
            sort_order: asc or desc
            search: Free text search across asset_tag (if present), brand, model, serial_number
            type: Filter by device_type
            status: Filter by status
            assigned_to: Filter by owner

        Returns:
            JSON object with 'data' (list of items) and 'meta' (pagination info).
        """
        page, page_size = _safe_page_params(args.get("page", 1), args.get("page_size", 20))
        sort_by = args.get("sort_by") or "created_at"
        sort_order = args.get("sort_order") or "desc"
        search = args.get("search")
        device_type = args.get("type")
        status = args.get("status")
        assigned_to = args.get("assigned_to")

        # Validate enums if provided (avoid leaking invalid values into query)
        if device_type and device_type not in DEVICE_TYPES:
            abort(400, message=f"Invalid type. Must be one of: {', '.join(DEVICE_TYPES)}")
        if status and status not in STATUS_TYPES:
            abort(400, message=f"Invalid status. Must be one of: {', '.join(STATUS_TYPES)}")

        try:
            with session_scope() as session:
                # Build base selectable
                base_stmt = select(InventoryItem)
                base_stmt = _apply_filters(base_stmt, search, device_type, status, assigned_to)
                # Count total
                count_stmt = select(func.count()).select_from(base_stmt.subquery())
                total = session.execute(count_stmt).scalar_one()
                # Sorting and pagination
                stmt = _apply_sorting(base_stmt, sort_by, sort_order)
                stmt = stmt.offset((page - 1) * page_size).limit(page_size)
                rows = session.execute(stmt).scalars().all()
                data = [r.to_dict() for r in rows]
                meta = _build_pagination_meta(total, page, page_size)
                return {"data": data, "meta": meta}
        except SQLAlchemyError as e:
            abort(500, message="Database error while fetching items.", errors={"detail": str(e)})

    @blp.arguments(InventoryItemCreateSchema)
    @blp.response(201, InventoryItemSchema)
    @blp.doc(summary="Create inventory item", description="Create a new inventory item.")
    def post(self, payload: Dict[str, Any]):
        """
        Create a new inventory item.

        Body:
            InventoryItemCreateSchema

        Returns:
            Created InventoryItem.
        """
        try:
            with session_scope() as session:
                item = InventoryItem(
                    device_type=payload["device_type"],
                    brand=payload.get("brand"),
                    model=payload.get("model"),
                    serial_number=payload.get("serial_number"),
                    owner=payload.get("owner"),
                    location=payload.get("location"),
                    status=payload.get("status", "available"),
                    notes=payload.get("notes"),
                )
                # If future model includes asset_tag, handle it gracefully
                if hasattr(InventoryItem, "asset_tag") and "asset_tag" in payload:
                    setattr(item, "asset_tag", payload.get("asset_tag"))

                session.add(item)
                session.flush()  # get id
                return item.to_dict()
        except IntegrityError as e:
            abort(409, message="Conflict: duplicate value detected.", errors={"detail": str(e)})
        except SQLAlchemyError as e:
            abort(500, message="Database error while creating item.", errors={"detail": str(e)})


@blp.route("/<int:item_id>")
class ItemDetailResource(MethodView):
    """Retrieve, update, and delete a single inventory item."""

    @blp.response(200, InventoryItemSchema)
    @blp.doc(summary="Get inventory item", description="Retrieve a single inventory item by ID.")
    def get(self, item_id: int):
        """
        Get an inventory item by id.

        Path:
            item_id: ID of the InventoryItem

        Returns:
            InventoryItem
        """
        try:
            with session_scope() as session:
                item = session.get(InventoryItem, item_id)
                if not item:
                    abort(404, message="Item not found.")
                return item.to_dict()
        except SQLAlchemyError as e:
            abort(500, message="Database error while retrieving item.", errors={"detail": str(e)})

    @blp.arguments(InventoryItemUpdateSchema)
    @blp.response(200, InventoryItemSchema)
    @blp.doc(summary="Update inventory item", description="Update an existing inventory item (partial updates supported).")
    def put(self, payload: Dict[str, Any], item_id: int):
        """
        Update an inventory item by id (PUT as idempotent partial update for simplicity).

        Path:
            item_id: ID of the InventoryItem

        Body:
            InventoryItemUpdateSchema (partial)

        Returns:
            Updated InventoryItem
        """
        # Re-run schema uniqueness validation with current_id if asset_tag present
        try:
            # The InventoryItemUpdateSchema.load override supports current_id param, but
            # flask-smorest already loaded payload; it's fine since _check_asset_tag_unique
            # is best-effort and model currently doesn't include asset_tag column.
            with session_scope() as session:
                item: Optional[InventoryItem] = session.get(InventoryItem, item_id)
                if not item:
                    abort(404, message="Item not found.")
                # Update fields present in payload
                updatable = ["device_type", "brand", "model", "serial_number", "owner", "location", "status", "notes"]
                for key in updatable:
                    if key in payload:
                        setattr(item, key, payload[key])
                if hasattr(InventoryItem, "asset_tag") and "asset_tag" in payload:
                    setattr(item, "asset_tag", payload.get("asset_tag"))
                session.add(item)
                session.flush()
                return item.to_dict()
        except IntegrityError as e:
            abort(409, message="Conflict: duplicate value detected.", errors={"detail": str(e)})
        except SQLAlchemyError as e:
            abort(500, message="Database error while updating item.", errors={"detail": str(e)})

    @blp.response(204)
    @blp.doc(summary="Delete inventory item", description="Delete an inventory item by ID.")
    def delete(self, item_id: int):
        """
        Delete an inventory item by id.

        Path:
            item_id: ID of the InventoryItem

        Returns:
            204 No Content
        """
        try:
            with session_scope() as session:
                item = session.get(InventoryItem, item_id)
                if not item:
                    abort(404, message="Item not found.")
                session.delete(item)
                # session_scope will commit
                return ""
        except SQLAlchemyError as e:
            abort(500, message="Database error while deleting item.", errors={"detail": str(e)})
