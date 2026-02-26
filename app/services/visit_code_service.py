from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.models.visit import Visit

_VLEERMUIS_FAMILY = "Vleermuis"


def compute_visit_code(visit: Visit) -> str | None:
    """Compute a condensed visit code for all species visits.

    For Vleermuis visits the code is:
    ``V{function_first_letter}{daypart}{visit_index}``
    where daypart is ``A`` (Avond) or ``O`` (Ochtend).

    For all other species the code is: ``{abbreviation}{visit_index}``.

    ``visit_index`` is taken from the linked ``ProtocolVisitWindow`` when
    available; otherwise falls back to ``visit.visit_nr`` (defaulting to 1).

    When a visit combines multiple qualifying species/function combinations all
    codes are returned space-separated, e.g. ``VMA2 VPA1``.

    Requires the visit to have ``species`` (with ``family`` loaded),
    ``functions``, and ``protocol_visit_windows`` (with ``protocol`` loaded)
    already eagerly loaded.

    Args:
        visit: Visit ORM instance with required relationships loaded.

    Returns:
        A space-separated string of visit codes, or ``None`` when none apply.
    """
    species_by_id = {s.id: s for s in (visit.species or [])}
    function_by_id = {f.id: f for f in (visit.functions or [])}

    part_of_day: str | None = getattr(visit, "part_of_day", None)
    if part_of_day == "Avond":
        daypart = "A"
    elif part_of_day == "Ochtend":
        daypart = "O"
    else:
        daypart = ""

    codes: list[str] = []
    pvws = visit.protocol_visit_windows or []

    if pvws:
        # Use PVWs for precise species/function/index mapping
        for pvw in pvws:
            protocol = getattr(pvw, "protocol", None)
            if protocol is None:
                continue

            species = species_by_id.get(protocol.species_id)
            if species is None:
                continue

            family_name: str | None = getattr(
                getattr(species, "family", None), "name", None
            )
            abbreviation: str | None = species.abbreviation
            is_vleermuis = family_name == _VLEERMUIS_FAMILY
            visit_index = pvw.visit_index

            if is_vleermuis:
                function = function_by_id.get(protocol.function_id)
                if function is None:
                    continue
                func_letter = "Z" if function.name == "Kraamverblijfplaats" else (function.name[0].upper() if function.name else "?")
                codes.append(f"V{func_letter}{daypart}{visit_index}")
            elif abbreviation:
                codes.append(f"{abbreviation}{visit_index}")
    else:
        # Fallback: no PVWs linked, use visit.species + visit.visit_nr
        visit_index = getattr(visit, "visit_nr", None) or 1
        for species in visit.species or []:
            family_name = getattr(
                getattr(species, "family", None), "name", None
            )
            abbreviation = species.abbreviation
            is_vleermuis = family_name == _VLEERMUIS_FAMILY

            if is_vleermuis:
                for function in visit.functions or []:
                    func_letter = "Z" if function.name == "Kraamverblijfplaats" else (function.name[0].upper() if function.name else "?")
                    codes.append(f"V{func_letter}{daypart}{visit_index}")
            elif abbreviation:
                codes.append(f"{abbreviation}{visit_index}")

    deduped_codes = list(dict.fromkeys(codes))
    return " ".join(deduped_codes) if deduped_codes else None
