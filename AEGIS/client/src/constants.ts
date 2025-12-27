export const CLOUD_PROVIDERS = ['openai', 'gemini'];

const apiBaseEnv = (import.meta.env.VITE_API_BASE_URL || '').trim();
let apiBase = apiBaseEnv || '/api';
while (apiBase.endsWith('/')) {
    apiBase = apiBase.slice(0, -1);
}
export const API_BASE_URL = apiBase;

export const CLOUD_MODEL_CHOICES: Record<string, string[]> = {
    openai: ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o"],
    gemini: [
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro",
        "gemini-1.5-pro-latest",
        "gemini-1.0-pro",
        "gemini-1.0-pro-vision",
    ],
};

export const AGENT_MODEL_CHOICES = [
    "gpt-oss:20b",
    "llama3.1:8b",
    "llama3.1:70b",
    "phi3.5:mini",
    "phi3.5:moe",
    "deepseek-r1:14b",
    "gemma3:27b",
];

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

// External API providers (non-GIBS)
export const EXTERNAL_LAYERS: Record<string, string> = {
    "OpenAQ_Air_Quality": "Air Quality (OpenAQ, Real-time)",
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
        description: 'Browse all available geospatial layers from NASA, air quality networks, and other sources.' 
    },
    { 
        id: 'gibs', 
        name: 'NASA GIBS', 
        description: 'NASA Global Imagery Browse Services provides satellite imagery and environmental data including temperature, vegetation, and atmospheric conditions.' 
    },
    { 
        id: 'openaq', 
        name: 'OpenAQ', 
        description: 'Real-time air quality measurements from monitoring stations worldwide, including PM2.5, ozone, and other pollutants.' 
    },
];

// Map each layer to its provider
export const LAYER_PROVIDERS: Record<string, string> = {
    // All GIBS layers map to 'gibs'
    ...Object.fromEntries(Object.keys(GIBS_NRT_LAYERS).map(k => [k, 'gibs'])),
    ...Object.fromEntries(Object.keys(GIBS_ANNUAL_LAYERS).map(k => [k, 'gibs'])),
    // External layers
    "OpenAQ_Air_Quality": "openaq",
};

// Combined layers for UI selection
export const COMMON_GEOSPATIAL_LAYERS: Record<string, string> = {
    ...GIBS_NRT_LAYERS,
    ...GIBS_ANNUAL_LAYERS,
    ...EXTERNAL_LAYERS,
};

export const COMMON_FOLIUM_MAPS: Record<string, string> = {
    "OpenStreetMap": "Street Map",
    "CartoDB Positron": "Cartographic Light",
    "CartoDB Dark_Matter": "Cartographic Dark",
    "Stamen Terrain": "Shaded Terrain",
    "Stamen Toner": "High-Contrast Toner",
    "Stamen Watercolor": "Watercolor Canvas",
    "Esri WorldImagery": "Esri World Imagery",
    "OpenTopoMap": "Topographic Relief",
    "Thunderforest.Transport": "Transit Network",
    "Jawg.Dark": "Jawg Dark",
    "Esri NatGeoWorldMap": "National Geographic",
    "Esri OceanBasemap": "Ocean Basemap",
};

export const MAX_GEOSPATIAL_LAYERS = 10;
