export const CLOUD_PROVIDERS = ['openai', 'gemini'];

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

export const COMMON_GEOSPATIAL_LAYERS: Record<string, string> = {
    "VIIRS_SNPP_CorrectedReflectance_TrueColor": "True Color (VIIRS SNPP)",
    "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual": "Land Cover (NLCD)",
    "SRTM_Color_Index": "Digital Elevation Model (SRTM)",
    "GPW_Population_Density_2020": "Population Density (GPW)",
    "MODIS_Terra_L3_Land_Water_Mask": "Hydrology (HydroSHEDS)",
    "IMERG_Precipitation_Rate": "Weather Radar (NEXRAD)",
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
