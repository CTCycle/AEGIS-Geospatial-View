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
  'rainviewer_precipitation_radar',
  'usgs_earthquakes',
  'noaa_weather_alerts',
  'fema_nfhl_flood_zones',
  'openmeteo_weather_forecast',
  'openaq_air_quality',
  'natural_earth_admin_boundaries',
  'census_acs_demographic_joins',
];

const requiredWebcamIds = [
  'windy_webcams_missing_key',
  'windy_webcams_points',
  'windy_webcams_popup',
  'windy_webcams_no_embed',
  'windy_webcams_stale',
  'windy_webcams_expired_preview',
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

assertContainsAll(readScenarioFile('geospatial-layers.spec.ts'), requiredLayerIds, 'geospatial-layers.spec.ts');
assertContainsAll(readScenarioFile('geospatial-webcams.spec.ts'), requiredWebcamIds, 'geospatial-webcams.spec.ts');

console.log('Geospatial e2e scenario catalog is complete.');
