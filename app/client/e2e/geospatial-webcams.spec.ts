export interface GeospatialWebcamScenario {
  id: string;
  description: string;
  expectedState: 'renders' | 'missing-credential' | 'metadata-only' | 'stale';
}

export const geospatialWebcamScenarios: GeospatialWebcamScenario[] = [
  { id: 'windy_webcams_missing_key', description: 'Windy Webcams reports missing credential without map failure', expectedState: 'missing-credential' },
  { id: 'windy_webcams_points', description: 'Windy webcam dots render from mocked metadata', expectedState: 'renders' },
  { id: 'windy_webcams_popup', description: 'Popup shows name, provider, preview when allowed, and official link', expectedState: 'renders' },
  { id: 'windy_webcams_popup_active_preview', description: 'Popup shows active preview, coordinates, attribution, and official source link', expectedState: 'renders' },
  { id: 'windy_webcams_popup_stale', description: 'Popup shows stale state without failing the camera layer', expectedState: 'stale' },
  { id: 'windy_webcams_popup_no_preview', description: 'Popup degrades to official link when preview media is missing or expired', expectedState: 'metadata-only' },
  { id: 'windy_webcams_no_embed', description: 'Embed is absent when terms do not explicitly allow embedding', expectedState: 'metadata-only' },
  { id: 'windy_webcams_allowed_embed', description: 'Embed appears only when provider permission explicitly allows it', expectedState: 'renders' },
  { id: 'windy_webcams_stale', description: 'Stale camera badge appears without failing the layer', expectedState: 'stale' },
  { id: 'windy_webcams_expired_preview', description: 'Expired preview refresh degrades to official link', expectedState: 'metadata-only' },
  { id: 'dot_traffic_camera_points', description: 'DOT traffic camera dots render from mocked agency metadata', expectedState: 'renders' },
  { id: 'tourism_camera_metadata_only', description: 'Tourism camera sources default to official links when embedding permission is unknown', expectedState: 'metadata-only' },
];
