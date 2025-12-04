import { useState } from 'react';
import './App.css';
import ConfigurationDrawer from './components/ConfigurationDrawer';
import LocationSearch from './components/LocationSearch';
import MapPreview from './components/MapPreview';
import StatusOutput from './components/StatusOutput';
import { RuntimeSettings, LocationSearchRequest, SearchResponsePayload } from './types';
import { searchLocation } from './services/api';

function App() {
    const [isDrawerOpen, setIsDrawerOpen] = useState(false);
    const [settings, setSettings] = useState<RuntimeSettings>({
        useCloudServices: false,
        provider: 'openai',
        cloudModel: 'gpt-4o',
        agentModel: 'llama3.1:8b',
        temperature: 0.7,
        reasoning: false,
    });

    const [isLoading, setIsLoading] = useState(false);
    const [searchResult, setSearchResult] = useState<{
        message?: string;
        json?: any;
        payload?: SearchResponsePayload;
    }>({});

    const handleSearch = async (request: LocationSearchRequest) => {
        setIsLoading(true);
        setSearchResult({}); // Clear previous results

        try {
            // Inject settings into request if needed, or backend handles it?
            // The backend seems to read from server settings, but the UI passed them in the original implementation
            // Wait, the original UI had settings in a drawer but the search endpoint doesn't seem to take them directly 
            // in the payload for /maps/search, except maybe implicitly or if I missed something.
            // Checking the backend `LocationSearchRequest` schema in `search.py`:
            // It takes: datetime, time_of_day, country, city, address, use_coordinates, latitude, longitude, filters, bbox...
            // It DOES NOT seem to take LLM settings. The LLM settings might be for a different endpoint or 
            // configured on the server.
            // However, `InterfaceService.handle_toggle_cloud_services` in `view.py` updated the UI state.
            // The `GeoSearchEndpointService.submit_location_search` sends `agentic_enabled`.
            // If agentic is enabled, maybe the backend uses the server-side configured model?
            // Let's look at `search.py` again. `search_by_location` endpoint.
            // It doesn't seem to take model params. 
            // BUT, `view.py` has `settings_controller`.
            // The `SettingsService` in `view.py` updates `runtime_config` which is imported from `AEGIS.server.utils.configurations.server`.
            // So the frontend was directly modifying server-side singleton configuration!
            // Since I cannot modify the backend code to accept these params in the request, and I cannot directly import python modules in React...
            // I might have a problem if the backend expects those settings to be set via a side-channel.
            // However, the prompt says "Refactor the frontend... Modify only files inside AEGIS\client and never touch the backend."
            // "Analyze the current communication pattern... replicate this behavior".
            // The original `view.py` was running IN THE SAME PROCESS as the server (or at least same python env) so it could modify `client_settings` and `server_settings` directly.
            // If I move to React, I am decoupled.
            // If the backend doesn't expose an endpoint to update settings, I can't update them.
            // Let's check if there is a settings endpoint.
            // I listed `AEGIS/server/endpoints` and saw `search.py`.
            // `app.py` includes `search_router`.
            // Is there another router?
            // `AEGIS/server/packages/configurations` seems to hold the state.
            // If the backend is stateless regarding per-request settings (which it should be for a REST API), then the settings should be passed in the request.
            // But `LocationSearchRequest` doesn't have them.
            // Maybe the "Agentic Assistant" feature uses them?
            // If the original app relied on shared memory state between "client" (NiceGUI) and "server" (FastAPI) running in the same process/module space, that is a tight coupling that breaks with a separate React frontend.
            // However, NiceGUI usually runs as a web server itself.
            // If `main.py` launches `launch_interface`, and `app.py` launches FastAPI.
            // `start_on_windows.bat` launches BOTH separately.
            // `python -m uvicorn AEGIS.server.app:app` (Backend)
            // `python -m AEGIS.client.main` (Frontend)
            // They are separate processes!
            // So how did `view.py` (Frontend process) affect `server_settings` (Backend process)?
            // `from AEGIS.server.utils.configurations import client_settings`
            // `from AEGIS.server.utils.configurations import server_settings`
            // If they are separate processes, importing `server_settings` in the client creates a COPY of that module in the client process. Modifying it there DOES NOT affect the backend process.
            // UNLESS:
            // 1. They are not separate processes (but the bat file says `start ... uvicorn` and `start ... client.main`).
            // 2. The backend reads from a file that the client writes to?
            // 3. The client passes the settings in the request headers or body, but I missed it?
            // 4. The "Agentic" feature runs LOCALLY in the client process?
            // Let's check `view.py` again.
            // `submit_location_search` calls `self.geo_search_controller.submit_location_search`.
            // `GeoSearchEndpointService.submit_location_search` sends a POST to `GEO_SEARCH_URL`.
            // It sends `agentic_enabled`.
            // It DOES NOT send model/provider.
            // So if the backend uses an LLM, where does it get the config?
            // Maybe `search.py` uses `server_settings`.
            // If `view.py` modifies `server_settings` in the CLIENT process, it shouldn't affect the SERVER process.
            // This suggests that either:
            // a) The "Agentic" logic that uses the LLM is actually running in the CLIENT (NiceGUI) and not the server?
            //    - `view.py` calls `geo_search_controller.submit_location_search`.
            //    - `GeoSearchEndpointService` makes an HTTP POST to the server.
            //    - So the logic is on the server.
            // b) The settings configuration in the UI was effectively doing nothing for the backend, or only affecting local client logic?
            //    - `InterfaceService` handles toggle cloud services. It updates `llm_provider_dropdown` etc.
            //    - `SettingsService.apply_runtime_settings` updates `self.runtime_config`.
            //    - `runtime_config` is `LLMRuntimeConfig`.
            //    - But this is all in the client memory.
            //    - Unless `LLMRuntimeConfig` writes to a file or DB?
            //    - Or maybe the "Agentic" feature is NOT implemented in `search.py`?
            //    - `search.py` has `process_location_search`.
            //    - It calls `renderer.build_satellite_payload`.
            //    - It returns `satellite_imagery`.
            //    - I don't see any LLM logic in `search.py`!
            //    - Wait, `AEGIS/server/packages/constants.py` has `GEO_AGENTIC_URL = "/maps/agentic"`.
            //    - `view.py` DOES NOT seem to call `/maps/agentic`.
            //    - `view.py` calls `submit_location_search` which posts to `GEO_SEARCH_URL` (`/maps/search`).
            //    - `search.py` handles `/maps/search`.
            //    - `search.py` imports `GIBSService`, `MapService`, `NormatimService`.
            //    - No LLM service imported in `search.py`.
            //    - So where is the Agentic stuff?
            //    - `view.py` has `agentic_checkbox`.
            //    - `submit_location_search` takes `agentic_enabled`.
            //    - `search.py` `LocationSearchRequest` has `agentic_enabled`.
            //    - But `search.py` `process_location_search` just calls `renderer.build_satellite_payload`.
            //    - `MapRenderingService.build_satellite_payload` calls `_render_base_map` and `_render_layer_overlays`.
            //    - I don't see any usage of `agentic_enabled` in `search.py` logic!
            //    - Maybe I missed it in `search.py`?
            //    - Let me check `search.py` again, specifically `process_location_search` or where `agentic_enabled` is used.

            // If the backend doesn't use it, then the settings in the UI might be placeholders or for future use?
            // OR, maybe I missed a file.
            // `AEGIS/server/endpoints/__init__.py`?
            // `AEGIS/server/app.py` only includes `search_router`.

            // Hypothesis: The "Agentic" feature is not fully implemented or I missed where it's hooked up.
            // However, my task is to REPLICATE the frontend.
            // So I should send the `agentic_enabled` flag and `agent_prompt` (if I added it) to the backend.
            // The `LocationSearchRequest` in `search.py` has `agentic_enabled`.
            // Does it have `agent_prompt`?
            // I need to check `AEGIS/server/schemas/geographics.py` to be sure about the payload structure.
            // But based on `view.py` `submit_location_search`:
            /*
                  result = await self.geo_search_controller.submit_location_search(
                      geospatial_filters,
                      selected_map_tiles,
                      country_input.value,
                      city_input.value,
                      address_input.value,
                      use_coordinates_switch.value,
                      latitude_input.value,
                      longitude_input.value,
                      search_datetime,
                      bool(agentic_checkbox.value),
                  )
            */
            // And `GeoSearchEndpointService.submit_location_search`:
            /*
              cleaned_payload = sanitize_search_payload(
                  geospatial_filters=geospatial_filters,
                  ...
                  agentic_enabled=agentic_enabled,
              )
            */
            // It doesn't seem to send the prompt text!
            // `view.py` has `llm_query_input` (Agent Prompt).
            // But `on_search_click` DOES NOT read `llm_query_input.value`!
            // It only reads `agentic_checkbox.value`.
            // So the prompt text is ignored in the current python implementation?
            // That's weird.
            // `llm_query_input` is defined but not passed to `submit_location_search`.

            // Okay, I will replicate this behavior (or lack thereof).
            // I will send `agentic_enabled`.
            // I will also send `agent_prompt` just in case I missed something or to be future proof, but strictly speaking the python code didn't seem to send it.
            // Wait, `sanitize_search_payload` might be doing something?
            // But `submit_location_search` signature doesn't take the prompt string.

            // So, regarding the Settings (Cloud provider, etc):
            // Since the frontend process is separate, and `view.py` was modifying local `runtime_config`, and the backend doesn't seem to receive these settings...
            // It implies the settings in the UI currently DO NOT affect the backend in the Python version either (unless they share a file/db, but `runtime_config` looked like in-memory).
            // So I will implement the UI for settings, manage the state in React, but I won't send them to the backend if the backend doesn't accept them.
            // I'll just keep them in the React state.

            const response = await searchLocation(request);
            setSearchResult({
                message: response.status_message,
                json: response.json || response.payload, // The backend returns { status_message, payload } and sometimes json?
                // In `GeoSearchEndpointService.submit_location_search`:
                // return {"json": data, "message": ...}
                // where `data` is the response from `trigger_search_maps` (the raw JSON from backend).
                // The backend returns `{"status_message": ..., "payload": ...}`.
                // So `response` here will be that object.
                payload: response.payload,
            });
        } catch (error: any) {
            setSearchResult({
                message: `Error${error.status ? ` ${error.status}` : ''}: ${error.message || 'Request failed'}`,
                json: error.detail || error.raw || error,
            });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="app-container">
            <ConfigurationDrawer
                isOpen={isDrawerOpen}
                onClose={() => setIsDrawerOpen(false)}
                settings={settings}
                onSettingsChange={setSettings}
            />

            <div
                className="drawer-toggle"
                onClick={() => setIsDrawerOpen(true)}
                title="Open Configuration"
            >
                <div className="drawer-toggle-bar"></div>
            </div>

            <div className="main-content">
                <h1 className="app-title">
                    AEGIS Geographics
                    <span className="app-subtitle">Visualize geographic data overlays in real time</span>
                </h1>

                <div className="content-grid">
                    <div className="left-column">
                        <LocationSearch onSearch={handleSearch} isLoading={isLoading} />
                    </div>

                    <div className="right-column">
                        <MapPreview payload={searchResult.payload} isLoading={isLoading} />
                    </div>
                </div>

                <div className="bottom-row">
                    <StatusOutput message={searchResult.message} json={searchResult.json || searchResult.payload} />
                </div>
            </div>
        </div>
    );
}

export default App;
