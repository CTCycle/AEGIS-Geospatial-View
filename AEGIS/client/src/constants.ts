export const CLOUD_PROVIDERS = ['openai', 'gemini'];

const apiBaseEnv = (import.meta.env.VITE_API_BASE_URL || '').trim();
export const API_BASE_URL = (apiBaseEnv || '/api').replace(/\/+$/, '');

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

export const GIBS_HOUSING_RELEVANT_LAYERS: Record<string, string> = {
    "Ground_Level_Nitrogen_Dioxide_3_Year_Running_Mean_2010-2012": "Air Pollution (NO2, 2010-2012)",
    "MODIS_Terra_Aerosol": "Aerosol Load (MODIS Terra)",
    "MODIS_Terra_Land_Surface_Temp_Day": "Land Surface Temperature Day (MODIS Terra)",
    "MODIS_Terra_NDVI_8Day": "Vegetation Index NDVI (8-day, MODIS Terra)",
    "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual": "Land Cover Type (MODIS IGBP)",
    "Landsat_Global_Man-made_Impervious_Surface": "Impervious Surface (GMIS, 30 m)",
    "SRTM_Color_Index": "Digital Elevation Model (SRTM)",
    "Landsat_Human_Built-up_And_Settlement_Extent": "Built-up & Roads (HBASE, Landsat)",
    "GPW_Population_Density_2020": "Population Density (GPW 2020)",
    "VIIRS_CityLights_2012": "Nighttime Lights (VIIRS)",
    "LECZ_Urban_Rural_Extents_Below_10m": "Low Elevation Coastal Zone (<10 m)",
};

export const COMMON_GEOSPATIAL_LAYERS: Record<string, string> = {
    "VIIRS_SNPP_CorrectedReflectance_TrueColor": "True Color (VIIRS SNPP)",
    "MODIS_Terra_L3_Land_Water_Mask": "Land/Water Mask (MODIS Terra)",
    "IMERG_Precipitation_Rate": "Precipitation Rate (IMERG)",
    ...GIBS_HOUSING_RELEVANT_LAYERS,
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
