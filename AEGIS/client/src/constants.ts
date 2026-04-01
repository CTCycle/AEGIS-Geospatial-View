const DEFAULT_API_BASE_URL = '/api';

const trimTrailingSlashes = (value: string): string => {
    let normalized = value;
    while (normalized.length > 1 && normalized.endsWith('/')) {
        normalized = normalized.slice(0, -1);
    }
    return normalized;
};

const normalizeApiBaseUrl = (value: string, isProduction: boolean): string => {
    const candidate = value.trim();
    if (!candidate) {
        return DEFAULT_API_BASE_URL;
    }

    if (candidate.startsWith('/') && !candidate.startsWith('//')) {
        return trimTrailingSlashes(candidate);
    }

    if (!isProduction && (candidate.startsWith('http://') || candidate.startsWith('https://'))) {
        return trimTrailingSlashes(candidate);
    }

    return DEFAULT_API_BASE_URL;
};

export const API_BASE_URL = normalizeApiBaseUrl(
    String(import.meta.env.VITE_API_BASE_URL || ''),
    Boolean(import.meta.env.PROD),
);

// Daily/NRT GIBS layers (updated frequently)
export const GIBS_NRT_LAYERS: Record<string, string> = {
    "VIIRS_SNPP_CorrectedReflectance_TrueColor": "True Color Satellite (VIIRS, Daily)",
    "MODIS_Terra_Aerosol": "Aerosol Optical Depth (MODIS, Daily)",
    "MODIS_Terra_Land_Surface_Temp_Day": "Surface Temperature Day (MODIS, Daily)",
    "MODIS_Terra_Land_Surface_Temp_Night": "Surface Temperature Night (MODIS, Daily)",
    "MODIS_Terra_NDVI_8Day": "Vegetation Index NDVI (MODIS, 8-day)",
    "MODIS_Terra_L3_Land_Water_Mask": "Land/Water Mask (MODIS, Daily)",
    "IMERG_Precipitation_Rate": "Precipitation Rate (IMERG, 30min)",
    "VIIRS_SNPP_DayNightBand_ENCC": "Nighttime Lights (VIIRS, Monthly)",
    "MODIS_Combined_Thermal_Anomalies_Fire": "Active Fires (MODIS, Daily)",
    "OMPS_Ozone_Total_Column": "Ozone Column (OMPS, Daily)",
};

// Annual/static GIBS layers (slow-changing data)
export const GIBS_ANNUAL_LAYERS: Record<string, string> = {
    "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual": "Land Cover Type (MODIS, Annual)",
    "SRTM_Color_Index": "Elevation DEM (SRTM)",
};

// Provider definitions with metadata
export type Provider = {
    id: string;
    name: string;
    description: string;
};

export const DATA_PROVIDERS: Provider[] = [
    {
        id: 'all',
        name: 'All Providers',
        description: 'Browse all available geospatial layers from NASA satellite and environmental datasets.'
    },
    {
        id: 'gibs',
        name: 'NASA GIBS',
        description: 'NASA Global Imagery Browse Services provides satellite imagery and environmental data including temperature, vegetation, and atmospheric conditions.'
    },
];

// Map each layer to its provider
export const LAYER_PROVIDERS: Record<string, string> = {
    // All GIBS layers map to 'gibs'
    ...Object.fromEntries(Object.keys(GIBS_NRT_LAYERS).map(k => [k, 'gibs'])),
    ...Object.fromEntries(Object.keys(GIBS_ANNUAL_LAYERS).map(k => [k, 'gibs'])),
};

// Combined layers for UI selection
export const COMMON_GEOSPATIAL_LAYERS: Record<string, string> = {
    ...GIBS_NRT_LAYERS,
    ...GIBS_ANNUAL_LAYERS,
};

export const COMMON_FOLIUM_MAPS: Record<string, string> = {
    "OpenStreetMap": "Street Map",
    "CartoDB Positron": "Cartographic Light",
    "CartoDB Dark_Matter": "Cartographic Dark",
    "Esri WorldImagery": "Esri World Imagery",
    "OpenTopoMap": "Topographic Relief",
    "Esri NatGeoWorldMap": "National Geographic",
    "Esri OceanBasemap": "Ocean Basemap",
};

export const MAX_GEOSPATIAL_LAYERS = 10;
