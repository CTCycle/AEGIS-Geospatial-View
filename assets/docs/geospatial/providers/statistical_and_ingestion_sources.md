# Statistical And Ingestion Sources

Last updated: 2026-06-02

## Downloadable And Ingestion-Oriented Sources

### OurAirports

Use for airport, heliport, and seaplane base reference data through downloadable CSV datasets.

- No API key is required.
- Ingest the CSV through the dataset-ingestion pipeline before exposing it as a searchable layer.
- Preserve attribution and source-vintage metadata.

### ArcGIS REST Services

Use for public and credentialed ArcGIS FeatureServer or MapServer layers.

- Prefer FeatureServer query endpoints with `f=geojson` for vector-friendly layers.
- Configure `ARCGIS_API_KEY` only for private or credentialed portals.
- Validate `maxRecordCount`, geometry support, and attribution before adding a manifest.

### U.S. Census Bureau

Use for U.S. Census Data API and TIGERweb geometry services.

- Public TIGERweb geometry can be used without a key.
- Request a Census API key only for higher-volume statistical API use.
- Geometry and statistical APIs must be joined by geography codes.

### Eurostat

Use for EU or EEA demographic, housing, rent, and economic indicators.

- No account is required for public API access.
- Use dataset-specific API URLs and JSON-stat responses.
- Results are statistical time series, not map geometry by themselves.

### FRED

Use for U.S. economic, housing, rent, and market indicators.

- Configure `FRED_API_KEY` or Access credentials.
- Review redistribution restrictions for third-party series.
- FRED provides time-series data, not direct geometry.

## Additional Classified Sources

The current source catalog also classifies or partially supports:

- Transitland
- Natural Earth
- Census cartographic boundaries
- Census ACS joins
- Eurostat GISCO NUTS
- Overture Maps
- OpenAddresses
- local parcel templates

These sources commonly participate in dataset-ingestion or metadata-only workflows rather than direct live map toggles.
