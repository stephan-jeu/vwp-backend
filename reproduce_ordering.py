
import sys
import os
import asyncio
from datetime import date, time
from dataclasses import dataclass, field

sys.path.append(os.getcwd())

from app.models.protocol import Protocol, ProtocolVisitWindow
from app.models.cluster import Cluster
from app.services.visit_generation_ortools import generate_visits_cp_sat

# Mocks
@dataclass
class MockFunction:
    name: str = "TestFunc"
    id: int = 1

@dataclass
class MockSpecies:
    abbreviation: str = "TS"
    name: str = "TestSpecies"
    family: object = None
    id: int = 1

@dataclass
class MockProtocol(Protocol):
    def __init__(self, id, min_period_val=0, min_period_unit="days"):
        self.id = id
        self.function = MockFunction()
        self.species = MockSpecies()
        self.visit_duration_hours = 1.0
        self.start_timing_reference = "ABSOLUTE_TIME" 
        self.start_time_absolute_from = time(10, 0)
        self.start_time_relative_minutes = 0
        self.end_timing_reference = None
        
        self.min_period_between_visits_value = min_period_val
        self.min_period_between_visits_unit = min_period_unit
        
        self.requires_morning_visit = False
        self.requires_evening_visit = False
        self.min_temperature_celsius = None
        self.max_wind_force_bft = None
        self.max_precipitation = None
        self.requires_june_visit = False
        self.requires_july_visit = False
        self.requires_maternity_period_visit = False
        
        # 2 Windows
        self.visit_windows = [
            ProtocolVisitWindow(id=100+id, protocol_id=id, visit_index=1, window_from=date(2025, 6, 1), window_to=date(2025, 6, 30)),
            ProtocolVisitWindow(id=200+id, protocol_id=id, visit_index=2, window_from=date(2025, 6, 1), window_to=date(2025, 6, 30))
        ]

    __tablename__ = 'protocols'

class MockDbSession:
    async def execute(self, stmt):
        class Result:
            def scalars(self):
                class All:
                    def all(self):
                        return []
                return All()
        return Result()
    def add(self, obj): pass
    async def flush(self): pass

async def test_ordering():
    print("Testing Ordering/Frequency Logic...")
    db = MockDbSession()
    cluster = Cluster(id=1)
    
    # Case: Gap is 0
    p1 = MockProtocol(id=1, min_period_val=0) # No enforced gap
    
    # The solver aims to minimize visits.
    # If gap is 0, it CAN put both requests in the SAME visit (since they share windows/properties).
    # Result: 1 visit containing BOTH Visit 1 and Visit 2?
    # Logic: req_start[v2] >= req_start[v1] + 0.
    # If same visit, req_start is same. Valid.
    
    visits, _ = await generate_visits_cp_sat(db, cluster, [p1])
    
    print(f"Generated {len(visits)} visits.")
    for v in visits:
        print(f"  Visit {v.visit_nr}: Date={v.from_date}, Protocols={[p.id for p in v.protocols]}")
        # Check if multiple indices
        indices = [p.visit_index for p in getattr(v, '_debug_reqs', [])] # We don't have easy access to indices in output objects directly without mapping
        # But we can infer from count.
        # Wait, generate_visits_cp_sat returns Visit objects. 
        # v.protocols will be list of protocol objects. Since it's the SAME protocol object, it appears twice?
        # unique_protos = list({r.protocol.id: r.protocol}.values())
        # So v.protocols has only 1 entry even if multiple requests?
        # Ah, unique_protos logic lines 499 in ortools:
        # unique_protos = list({r.protocol.id: r.protocol for r in assigned_reqs}.values())
        # So yes, only 1 protocol in the list.
    
    # If len(visits) == 1, it means both requests were squashed into 1 visit.
    # This violates "At least a week between visits".
    
    if len(visits) == 1:
        print("FAILURE: Both protocol visits grouped into ONE visit (Gap=0 allowed this).")
    elif len(visits) == 2:
        v1 = visits[0]
        v2 = visits[1]
        gap = (v2.from_date - v1.from_date).days
        print(f"Gap between visits: {gap} days")
        if gap < 7:
             print("FAILURE: Gap < 7 days")
        else:
             print("SUCCESS: Gap >= 7 days")

if __name__ == "__main__":
    asyncio.run(test_ordering())
