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
  { id: 'rainviewer_precipitation_radar', description: 'RainViewer radar uses latest or stale frame', expectedState: 'stale-fallback' },
  { id: 'usgs_earthquakes', description: 'USGS earthquake GeoJSON points render', expectedState: 'renders' },
  { id: 'noaa_weather_alerts', description: 'NOAA weather alert polygons render', expectedState: 'renders' },
  { id: 'fema_nfhl_flood_zones', description: 'FEMA flood hazard overlay renders', expectedState: 'renders' },
  { id: 'openmeteo_weather_forecast', description: 'Open-Meteo sampled weather layer handles empty responses', expectedState: 'empty' },
  { id: 'openaq_air_quality', description: 'OpenAQ missing key or station response is handled', expectedState: 'missing-credential' },
  { id: 'natural_earth_admin_boundaries', description: 'Natural Earth vector tile descriptor renders', expectedState: 'renders' },
  { id: 'census_acs_demographic_joins', description: 'ACS choropleth descriptor renders when joined data exists', expectedState: 'renders' },
];
