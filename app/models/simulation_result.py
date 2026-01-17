from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Column, Integer, Date, JSON
from app.models import Base, TimestampMixin

class SimulationResult(Base, TimestampMixin):
    __tablename__ = "simulation_results"
    
    id = Column(Integer, primary_key=True, index=True)
    
    horizon_start = Column(Date, nullable=False)
    horizon_end = Column(Date, nullable=False)
    
    # Store the complex nested structure as JSON
    # Structure:
    # {
    #   "deadline_view": { ... },
    #   "week_view": { ... }
    # }
    grid_data = Column(JSON, nullable=False)
