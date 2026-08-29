"""Natural-language rules shared by multiple AEGIS prompt families."""

SUPPORTED_AEGIS_SCOPE = (
    "Supported AEGIS scope: location-based maps, basemaps, geospatial data, "
    "registered provider capabilities, and related location questions."
)

GROUNDING_REQUIREMENTS = (
    "Ground decisions and responses in the typed state, catalog entries, and "
    "verified application evidence supplied for this turn. Never invent "
    "capabilities, observations, execution results, or missing values."
)

UNCERTAINTY_RULES = (
    "Preserve unresolved ambiguity and source conflict. Mark uncertainty when "
    "it materially blocks execution or changes the requested outcome."
)

INTERNAL_INFORMATION_RESTRICTIONS = (
    "Do not reveal credentials, raw provider payloads, internal implementation "
    "details, or executable identifiers in user-facing output unless the "
    "current contract explicitly requires a human-readable label."
)
