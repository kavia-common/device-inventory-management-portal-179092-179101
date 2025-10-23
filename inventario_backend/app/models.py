"""
SQLAlchemy models for the Inventario backend.

Defines the InventoryItem model mapping to the database table for device inventory.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, Text


class Base(DeclarativeBase):
    """Declarative base for SQLAlchemy models."""
    pass


class InventoryItem(Base):
    """
    Inventory item representing a device record in the inventory.

    Fields are designed to match the expected schema defined in schema.sql:
    - id: Primary key
    - device_type: Type of device (laptop, monitor, docking, mouse, etc.)
    - brand: Brand or manufacturer
    - model: Model identifier
    - serial_number: Device serial number (unique where possible)
    - owner: Person or department owning the device
    - location: Physical location
    - status: Current status (available, assigned, repair, retired)
    - notes: Free-form notes
    - created_at: Record creation timestamp
    - updated_at: Record last update timestamp
    """

    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(100), default=None)
    model: Mapped[Optional[str]] = mapped_column(String(100), default=None)
    serial_number: Mapped[Optional[str]] = mapped_column(String(120), unique=False, index=True, default=None)
    owner: Mapped[Optional[str]] = mapped_column(String(120), default=None)
    location: Mapped[Optional[str]] = mapped_column(String(120), default=None)
    status: Mapped[Optional[str]] = mapped_column(String(50), default="available")
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # PUBLIC_INTERFACE
    def to_dict(self) -> dict:
        """Serialize the InventoryItem to a dict suitable for JSON responses."""
        return {
            "id": self.id,
            "device_type": self.device_type,
            "brand": self.brand,
            "model": self.model,
            "serial_number": self.serial_number,
            "owner": self.owner,
            "location": self.location,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
