const fs = require('node:fs');
const path = require('node:path');

const requiredLayerIds = [
  'osm_default',
  'osm_dark',
  'osm_terrain',
  'gibs_satellite',
  'tomtom_basic',
  'geoapify_osm',
  'VIIRS_SNPP_CorrectedReflectance_TrueColor',
  'SRTM_Color_Index',
  'IMERG_Precipitation_Rate',
  'MODIS_Combined_Thermal_Anomalies_Fire',
  'OMPS_Ozone_Total_Column',
  'rainviewer_precipitation_radar',
  'tomtom_traffic_flow',
  'geoapify_amenities',
  'overpass_poi_amenities',
  'openmeteo_air_quality_forecast',
  'openmeteo_pressure_humidity_wind',
  'usgs_earthquakes',
  'noaa_weather_alerts',
  'noaa_radar',
  'fema_nfhl_flood_zones',
  'usgs_water_gauges',
  'noaa_coops_water_levels',
  'openmeteo_weather_forecast',
  'openaq_air_quality',
  'nasa_firms_active_fires',
  'natural_earth_admin_boundaries',
  'census_cartographic_boundaries',
  'census_acs_demographic_joins',
  'eurostat_nuts_regions',
  'gtfs_static',
  'gtfs_realtime',
  'openchargemap_ev_charging',
  'nrel_afdc_alt_fuel_stations',
  'opentripmap_tourism_pois',
  'ourairports_airports',
];

const requiredWebcamIds = [
  'windy_webcams_missing_key',
  'windy_webcams_points',
  'windy_webcams_popup',
  'windy_webcams_no_embed',
  'windy_webcams_allowed_embed',
  'windy_webcams_stale',
  'windy_webcams_expired_preview',
  'dot_traffic_camera_points',
  'tourism_camera_metadata_only',
];

function readScenarioFile(fileName) {
  const fullPath = path.join(__dirname, fileName);
  return fs.readFileSync(fullPath, 'utf8');
}

function assertContainsAll(content, ids, fileName) {
  const missing = ids.filter((id) => !content.includes(id));
  if (missing.length) {
    throw new Error(`${fileName} is missing scenarios: ${missing.join(', ')}`);
  }
}

function assertBrowserSmokeExists() {
  const fullPath = path.join(__dirname, '..', 'src', 'app', 'e2e', 'geospatial-browser-smoke.spec.ts');
  const content = fs.readFileSync(fullPath, 'utf8');
  assertContainsAll(content, [
    'DEFAULT_BASE_TILE_PROXY_URL',
    'mock_clustered_points',
    'metadata_context',
    'windy_webcams_missing_key',
    'forbiddenSecret',
  ], 'src/app/e2e/geospatial-browser-smoke.spec.ts');
}

assertContainsAll(readScenarioFile('geospatial-layers.spec.ts'), requiredLayerIds, 'geospatial-layers.spec.ts');
assertContainsAll(readScenarioFile('geospatial-webcams.spec.ts'), requiredWebcamIds, 'geospatial-webcams.spec.ts');
assertBrowserSmokeExists();

console.log('Geospatial e2e scenario catalog and browser smoke coverage are complete.');
