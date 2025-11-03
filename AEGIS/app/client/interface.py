from __future__ import annotations

import json
from datetime import datetime
from functools import partial
from typing import Any

from nicegui import ui

from AEGIS.app.client.layouts import (
    CARD_BASE_CLASSES,
    INTERFACE_THEME_CSS,
    PAGE_CONTAINER_CLASSES,
)
from AEGIS.app.client.controllers import (
    get_runtime_settings,
    resolve_cloud_selection,
    submit_location_search,
)
from AEGIS.app.constants import AGENT_MODEL_CHOICES, FILTER_CHOICES, CLOUD_MODEL_CHOICES

CLOUD_PROVIDERS: list[str] = [key for key in CLOUD_MODEL_CHOICES]

###############################################################################
# HELPERS
###############################################################################
def get_datetime_default_value() -> str:
    current = datetime.now().replace(second=0, microsecond=0)
    return current.isoformat(timespec="minutes")

# -----------------------------------------------------------------------------
async def handle_toggle_cloud_services(
    llm_provider_dropdown: Any,
    cloud_model_dropdown: Any,
    agent_model_dropdown: Any,    
    temperature_input: Any,
    reasoning_checkbox: Any,  
    event: Any,
) -> None:
    enabled = bool(event.value)
    selection = resolve_cloud_selection(
        str(llm_provider_dropdown.value or ""),
        str(cloud_model_dropdown.value or ""),
    )
    llm_provider_dropdown.value = selection["provider"]
    llm_provider_dropdown.update()
    cloud_model_dropdown.set_options(selection["models"])
    cloud_model_dropdown.value = selection["model"]
    cloud_model_dropdown.update()
    if enabled:
        llm_provider_dropdown.enable()
        cloud_model_dropdown.enable()        
        agent_model_dropdown.disable()        
        temperature_input.disable()
        reasoning_checkbox.disable()
    else:
        llm_provider_dropdown.disable()
        cloud_model_dropdown.disable()
        agent_model_dropdown.enable() 
        temperature_input.enable()
        reasoning_checkbox.enable()

# -----------------------------------------------------------------------------
async def handle_cloud_provider_change(
    llm_provider_dropdown: Any,
    cloud_model_dropdown: Any,
    event: Any,
) -> None:
    selection = resolve_cloud_selection(
        str(event.value or ""),
        str(cloud_model_dropdown.value or ""),
    )
    llm_provider_dropdown.value = selection["provider"]
    llm_provider_dropdown.update()
    cloud_model_dropdown.set_options(selection["models"])
    cloud_model_dropdown.value = selection["model"]
    cloud_model_dropdown.update()

# -----------------------------------------------------------------------------
def update_status_with_json(status_display: Any, message: str, payload: Any) -> None:
    # Build a single Markdown block with status + pretty JSON (if present).
    parts: list[str] = []
    if message:
        parts.append(message.strip())
    if payload is not None:
        formatted = json.dumps(payload, indent=2, sort_keys=True, default=str)
        parts.append(f"```json\n{formatted}\n```")
    content = "\n\n".join(parts) if parts else "Waiting for response..."
    status_display.set_content(content)

# -----------------------------------------------------------------------------
async def on_use_coordinates_change(
    event: Any,
    *,
    country_input: Any,
    city_input: Any,
    address_input: Any,
    latitude_input: Any,
    longitude_input: Any,
) -> None:
    use_coordinates = getattr(event, "value", event)
    if use_coordinates:
        country_input.value = ""
        city_input.value = ""
        address_input.value = ""
        country_input.disable()
        city_input.disable()
        address_input.disable()
        latitude_input.enable()
        longitude_input.enable()
    else:
        country_input.enable()
        city_input.enable()
        address_input.enable()
        latitude_input.value = None
        longitude_input.value = None
        latitude_input.disable()
        longitude_input.disable()


# -----------------------------------------------------------------------------
async def on_search_click(
    event: Any,
    *,
    filter_select: Any,
    country_input: Any,
    city_input: Any,
    address_input: Any,
    use_coordinates_switch: Any,
    latitude_input: Any,
    longitude_input: Any,
    date_input: Any,
    status_display: Any,
) -> None:
    del event
    result = await submit_location_search(
        filter_select.value,
        country_input.value,
        city_input.value,
        address_input.value,
        use_coordinates_switch.value,
        latitude_input.value,
        longitude_input.value,
        date_input.value,
    )
    message = result.get("message") or "Location search payload submitted."
    # Push both status and JSON directly into the status display panel
    update_status_with_json(status_display, message, result.get("json"))

###############################################################################
# MAIN UI PAGE
###############################################################################
def main_page() -> None:
    current_settings = get_runtime_settings()
    selection = resolve_cloud_selection(
        current_settings.provider, current_settings.cloud_model
    )
    provider = selection["provider"]
    cloud_models = selection["models"]
    selected_cloud_model = selection["model"]
    cloud_enabled = current_settings.use_cloud_services

    ui.page_title("AEGIS Geographics")
    ui.add_head_html(f"<style>{INTERFACE_THEME_CSS}</style>")

    with ui.column().classes(PAGE_CONTAINER_CLASSES):
        ui.markdown(
            "## AEGIS Geographics\nVisualize geographic data overlays in real time"
        ).classes("text-3xl font-semibold text-slate-800 dark:text-slate-100")
        with ui.row().classes("w-full flex-wrap justify-start"):
            with ui.card().classes(f"{CARD_BASE_CLASSES} w-full"):
                with ui.column().classes("gap-4"):
                    ui.markdown("**Authentication**")
                    auth_button = ui.button("Authenticate", on_click=None)
                    auth_button.props("color=secondary")
                    auth_button.props("size=sm")

        with ui.row().classes("w-full gap-6 items-stretch flex-wrap md:flex-nowrap"):
            with ui.card().classes(f"{CARD_BASE_CLASSES} flex-1 w-full md:w-1/2"):
                with ui.column().classes("gap-4 h-full"):
                    ui.markdown("### Location search")

                    with ui.column().classes("gap-3"):
                        use_coordinates_switch = ui.switch(
                            "Provide latitude and longitude"
                        ).props("color=primary")

                        country_input = ui.input(
                            label="Country or Region",
                            placeholder="Enter a country or region",
                        ).classes("w-full")

                        city_input = ui.input(
                            label="City Name",
                            placeholder="Enter a city or locale",
                        ).classes("w-full")

                        address_input = (
                            ui.input(
                                label="Street Address",
                                placeholder="Enter the specific address",
                            )
                            .classes("w-full")
                            .props("required")
                        )

                        with ui.row().classes("w-full gap-3 flex-wrap"):
                            latitude_input = ui.number(
                                label="Latitude (°)",
                                format="%.6f",
                                step=0.000001,
                            ).classes("flex-1 min-w-[160px]")
                            longitude_input = ui.number(
                                label="Longitude (°)",
                                format="%.6f",
                                step=0.000001,
                            ).classes("flex-1 min-w-[160px]")

                        date_input = ui.input(label="Reference Moment")
                        date_input.props["type"] = "datetime-local"
                        date_input.set_value(get_datetime_default_value())

                        filter_select = ui.select(
                            FILTER_CHOICES,
                            label="Imagery Style",
                        ).classes("w-full")

                    ui.space()
                    search_button = ui.button("Start search", on_click=None).props(
                        "color=primary"
                    )

            with ui.card().classes(f"{CARD_BASE_CLASSES} flex-1 w-full md:w-1/2"):
                with ui.column().classes("gap-3 h-full"):
                    ui.markdown("### Agentic Search")
                    agentic_checkbox = ui.checkbox("Activate agentic assistant")
                    llm_query_input = ui.textarea(
                        label="Agent Prompt",
                        placeholder="Describe the geographic insights you need",
                    ).classes("w-full")

                    with ui.expansion("Models Configuration").classes("w-full"):
                        ui.label("Configuration").classes("aegis-card-title")                        
                        use_cloud_services = ui.checkbox(
                            "Use Cloud Services",
                            value=cloud_enabled,
                        ).classes("pt-2")
                        with ui.grid(columns=1).classes("w-full gap-5 lg:grid-cols-2"):
                            with ui.column().classes("w-full gap-3"):
                                ui.label("Cloud Configuration").classes("aegis-subtitle")
                                llm_provider_dropdown = ui.select(
                                    CLOUD_PROVIDERS,
                                    label="Cloud Service",
                                    value=provider,
                                ).classes("w-full")
                                cloud_model_dropdown = ui.select(
                                    cloud_models,
                                    label="Cloud Model",
                                    value=selected_cloud_model or None,
                                ).classes("w-full")
                            with ui.column().classes("w-full gap-3"):
                                ui.label("Ollama Configuration").classes(
                                    "aegis-subtitle"
                                )
                                agent_model_dropdown = ui.select(
                                    AGENT_MODEL_CHOICES,
                                    label="Parsing Model",
                                    value=current_settings.agent_model,
                                ).classes("w-full")                                
                                temperature_input = ui.number(
                                    label="Temperature",
                                    value=current_settings.temperature,
                                    min=0.0,
                                    max=5.0,
                                    step=0.1,
                                ).classes("w-full")
                                reasoning_checkbox = ui.checkbox(
                                    "Enable reasoning (think)",
                                    value=current_settings.reasoning,
                                )                                

                    ui.space()
                    agentic_button = ui.button(
                        "Run agentic search", on_click=None
                    ).props("color=secondary")

        with ui.row().classes("w-full gap-4 items-stretch flex-wrap md:flex-nowrap"):
            with ui.card().classes(f"{CARD_BASE_CLASSES} flex-1 min-w-0 w-full md:w-1/2"):
                with ui.column().classes("gap-3 h-full"):
                    ui.markdown("### Map Preview")
                    map_canvas = ui.image()
                    map_canvas.classes(
                        "w-full h-full min-h-[560px] max-h-[800px] object-contain bg-slate-100"
                    )

            with ui.card().classes(f"{CARD_BASE_CLASSES} flex-1 min-w-0 w-full md:w-1/2"):
                with ui.column().classes("gap-3 h-full"):
                    ui.markdown("### Endpoint Output")
                    with ui.scroll_area().classes("w-full h-full max-h-[360px] min-w-0"):
                        status_display = ui.markdown("Waiting for response...")
                        status_display.classes("status-output w-full text-sm font-mono")

    
    use_cloud_services.on_value_change(
        partial(
            handle_toggle_cloud_services,
            llm_provider_dropdown,
            cloud_model_dropdown,
            agent_model_dropdown,           
            temperature_input,
            reasoning_checkbox,           
        )
    )
    llm_provider_dropdown.on_value_change(
        partial(
            handle_cloud_provider_change, 
            llm_provider_dropdown, 
            cloud_model_dropdown)
    )   
   
    use_coordinates_switch.on_value_change(
        partial(
            on_use_coordinates_change,
            country_input=country_input,
            city_input=city_input,
            address_input=address_input,
            latitude_input=latitude_input,
            longitude_input=longitude_input,
        )
    )
    search_button.on_click(
        partial(
            on_search_click,
            filter_select=filter_select,
            country_input=country_input,
            city_input=city_input,
            address_input=address_input,
            use_coordinates_switch=use_coordinates_switch,
            latitude_input=latitude_input,
            longitude_input=longitude_input,
            date_input=date_input,
            status_display=status_display,
        )
    )
    

###############################################################################
# MOUNT AND LAUNCH
###############################################################################
def create_interface() -> None:
    ui.page("/")(main_page)

# -----------------------------------------------------------------------------
def launch_interface() -> None:
    create_interface()
    ui.run(
        host="0.0.0.0",
        port=7861,
        title="AEGIS Geographics",
        show_welcome_message=False,
    )

# -----------------------------------------------------------------------------
if __name__ in {"__main__", "__mp_main__"}:
    launch_interface()
