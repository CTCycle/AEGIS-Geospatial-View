export interface GeospatialLayerScenario {
  id: string;
  description: string;
  expectedState: 'renders' | 'missing-credential' | 'empty' | 'stale-fallback';
}

export const geospatialLayerScenarios: GeospatialLayerScenario[] = [
  { id: 'osm_default', description: 'Default OSM basemap renders', expectedState: 'renders' },
  { id: 'osm_dark', description: 'Dark OSM basemap renders', expectedState: 'renders' },
  { id: 'osm_terrain', description: 'Terrain basemap renders', expectedState: 'renders' },
  { id: 'gibs_satellite', description: 'GIBS satellite basemap renders', expectedState: 'renders' },
  { id: 'tomtom_basic', description: 'TomTom missing key is shown without breaking map', expectedState: 'missing-credential' },
  { id: 'geoapify_osm', description: 'Geoapify missing key is shown without breaking map', expectedState: 'missing-credential' },
  { id: 'VIIRS_SNPP_CorrectedReflectance_TrueColor', description: 'NASA GIBS true color overlay renders', expectedState: 'renders' },
  { id: 'SRTM_Color_Index', description: 'NASA GIBS terrain color overlay renders', expectedState: 'renders' },
  { id: 'IMERG_Precipitation_Rate', description: 'NASA GIBS precipitation overlay renders', expectedState: 'renders' },
  { id: 'MODIS_Combined_Thermal_Anomalies_Fire', description: 'NASA GIBS fire anomaly overlay renders', expectedState: 'renders' },
  { id: 'OMPS_Ozone_Total_Column', description: 'NASA GIBS ozone overlay renders', expectedState: 'renders' },
  { id: 'rainviewer_precipitation_radar', description: 'RainViewer radar uses latest or stale frame', expectedState: 'stale-fallback' },
  { id: 'tomtom_traffic_flow', description: 'TomTom traffic flow handles missing credentials or mocked tiles', expectedState: 'missing-credential' },
  { id: 'geoapify_amenities', description: 'Geoapify amenities handles missing credentials or mocked vector points', expectedState: 'missing-credential' },
  { id: 'overpass_poi_amenities', description: 'Overpass amenity POIs render from mocked bounded responses', expectedState: 'renders' },
  { id: 'openmeteo_air_quality_forecast', description: 'Open-Meteo air quality sampled layer handles empty responses', expectedState: 'empty' },
  { id: 'openmeteo_pressure_humidity_wind', description: 'Open-Meteo wind and pressure sampled layer handles empty responses', expectedState: 'empty' },
  { id: 'usgs_earthquakes', description: 'USGS earthquake GeoJSON points render', expectedState: 'renders' },
  { id: 'noaa_weather_alerts', description: 'NOAA weather alert polygons render', expectedState: 'renders' },
  { id: 'noaa_radar', description: 'NOAA radar descriptor renders without breaking other overlays', expectedState: 'renders' },
  { id: 'fema_nfhl_flood_zones', description: 'FEMA flood hazard overlay renders', expectedState: 'renders' },
  { id: 'usgs_water_gauges', description: 'USGS water gauges render as clustered points', expectedState: 'renders' },
  { id: 'noaa_coops_water_levels', description: 'NOAA CO-OPS water stations render as clustered points', expectedState: 'renders' },
  { id: 'openmeteo_weather_forecast', description: 'Open-Meteo sampled weather layer handles empty responses', expectedState: 'empty' },
  { id: 'openaq_air_quality', description: 'OpenAQ missing key or station response is handled', expectedState: 'missing-credential' },
  { id: 'nasa_firms_active_fires', description: 'NASA FIRMS fire points handle missing credentials or mocked detections', expectedState: 'missing-credential' },
  { id: 'natural_earth_admin_boundaries', description: 'Natural Earth vector tile descriptor renders', expectedState: 'renders' },
  { id: 'census_cartographic_boundaries', description: 'Census cartographic boundary descriptor renders', expectedState: 'renders' },
  { id: 'census_acs_demographic_joins', description: 'ACS choropleth descriptor renders when joined data exists', expectedState: 'renders' },
  { id: 'eurostat_nuts_regions', description: 'Eurostat NUTS regions descriptor renders', expectedState: 'renders' },
  { id: 'gtfs_static', description: 'GTFS static stops and routes render from fixture data', expectedState: 'renders' },
  { id: 'gtfs_realtime', description: 'GTFS realtime alerts and vehicles render from mocked protobuf fixtures', expectedState: 'renders' },
  { id: 'openchargemap_ev_charging', description: 'Open Charge Map EV charging points render from mocked provider data', expectedState: 'renders' },
  { id: 'nrel_afdc_alt_fuel_stations', description: 'NREL AFDC stations handle missing key or mocked provider data', expectedState: 'missing-credential' },
  { id: 'opentripmap_tourism_pois', description: 'OpenTripMap tourism POIs handle missing key or mocked provider data', expectedState: 'missing-credential' },
  { id: 'ourairports_airports', description: 'OurAirports airports render after dataset ingestion', expectedState: 'renders' },
];
