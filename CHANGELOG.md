# Changelog

All notable changes to Ship Port Distance Helper are documented here.

The version number lives in `version.py` and is shown in the app window.

## [0.27] - 2026-09-02

### Changed

-   The "all ports" checkbox (both analyzers) no longer analyzes ALL ports x ALL ports, which flooded the output with pairs between two non-load ports (60,000+ missing distances that no voyage needs).
-   New scope when checked: every pair involving at least one load port — i.e. all load ports x all ports AND all ports x all load ports (the same pairs mirrored) — each pair analyzed exactly once.
-   Checkbox renamed to "All load ports x ALL ports (each pair once)"; analysis mode in the summary now reads "ALL LOAD PORTS x ALL ports (each pair once)".

## [0.26] - 2026-09-02

### Added

-   Complex Distances Analyzer: same "Analyse ALL ports (not only load ports)" checkbox as the Simple Analyzer.
    -   Unchecked (default): unchanged behavior — analysis between load ports and all ports.
    -   Checked: every port is treated as an origin, and each pair of ports is analyzed exactly once (rule matching and segment lookups are symmetric).
    -   The summary output now shows which analysis mode was used.

## [0.25] - 2026-09-02

### Added

-   Simple Distances Analyzer: new "Analyse ALL ports (not only load ports)" checkbox.
    -   Unchecked (default): unchanged behavior — missing distances between load ports and all ports.
    -   Checked: missing distances between ALL ports and ALL ports (useful when activating a port with load = TRUE). Each pair is reported once, since one distance row covers both directions.
    -   The summary output now shows which analysis mode was used.

## [0.24] - 2026-09-02

Versioning starts here. Current state of the app:

-   Launcher GUI with two tools: Simple Distances Analyzer (load to disch) and Complex Distances Analyzer (A-Z & Segments)
-   Ports CSV + Complete Distances CSV loading, optional inclusion of inactive ports
-   Progress bar, summary and missing distances output, copy to clipboard / TSV export
-   `fill_ports_coordinates.py` helper script to geocode ports without coordinates (Nominatim / OpenStreetMap)
