from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any
from collections.abc import Callable  

from DILIGENT.app.constants import OPENAI_CLOUD_MODELS
from nicegui import ui

from AEGIS.app.client.layouts import INTERFACE_THEME_CSS, PAGE_CONTAINER_CLASSES
from AEGIS.app.configurations import ClientRuntimeConfig
from AEGIS.app.client.controllers import (
    ComponentUpdate,
    MISSING,
    set_agentic_mode,
    set_cloud_model_mode,
    set_location_mode,
    submit_location_search,
)
from AEGIS.app.constants import AGENT_MODEL_CHOICES, FILTER_CHOICES, CLOUD_MODEL_CHOICES

CLOUD_PROVIDERS : list[str] = [k for k in CLOUD_MODEL_CHOICES.keys()]

###############################################################################
@dataclass
class ClientComponents:
    auth_button: Any
    country: Any
    city: Any
    address: Any
    use_coordinates: Any
    latitude: Any
    longitude: Any
    date: Any
    filter: Any
    search: Any
    agentic_toggle: Any
    llm_query: Any
    use_cloud: Any
    openai_model: Any
    agent_model: Any
    temperature: Any
    agentic: Any
    status: Any
    map_display: Any

# HELPERS
###############################################################################
def sanitized_text(value: Any) -> str:    
    return str(value or "").strip()

# -----------------------------------------------------------------------------
def get_datetime_default_value() -> str:
    current = datetime.now().replace(second=0, microsecond=0)
    return current.isoformat(timespec="minutes")

# UPDATES
###############################################################################
def apply_component_update(component: Any, update: ComponentUpdate) -> None:    
    if component is None:
        return
    if update.value is not MISSING:
        if hasattr(component, "set_value"):
            component.set_value(update.value)
        elif hasattr(component, "set_content"):
            component.set_content(update.value)
        else:
            component.value = update.value
    if update.enabled is not None:
        if update.enabled and hasattr(component, "enable"):
            component.enable()
        elif not update.enabled and hasattr(component, "disable"):
            component.disable()
    if update.visible is not None and hasattr(component, "visible"):
        component.visible = update.visible
    if update.minimum is not None and hasattr(component, "props"):
        component.props["min"] = update.minimum
    if update.maximum is not None and hasattr(component, "props"):
        component.props["max"] = update.maximum
    if hasattr(component, "update"):
        component.update()

# -----------------------------------------------------------------------------
def format_status_output(data: dict[str, Any] | None, message: str) -> str:
    if not data:
        return message
    payload = data.get("payload") if isinstance(data, dict) else None
    if isinstance(payload, dict):
        serialized = json.dumps(payload, indent=2, sort_keys=True)
        return f"{message}\n\n```json\n{serialized}\n```"
    return message

# -----------------------------------------------------------------------------
async def handle_use_coordinates_change(components: ClientComponents, event: Any) -> None:
    use_coordinates = bool(event.value)
    updates = set_location_mode(use_coordinates)
    apply_component_update(components.country, updates["country"])
    apply_component_update(components.city, updates["city"])
    apply_component_update(components.address, updates["address"])
    apply_component_update(components.latitude, updates["latitude"])
    apply_component_update(components.longitude, updates["longitude"])

# -----------------------------------------------------------------------------
async def handle_agentic_toggle(components: ClientComponents, event: Any) -> None:    
    agentic_enabled = bool(event.value)
    use_coordinates = bool(components.use_coordinates.value)
    updates = set_agentic_mode(agentic_enabled, use_coordinates)
    apply_component_update(components.llm_query, updates["llm_query"])
    apply_component_update(components.use_cloud, updates["use_cloud"])
    apply_component_update(components.openai_model, updates["openai_model"])
    apply_component_update(components.agent_model, updates["agent_model"])
    apply_component_update(components.temperature, updates["temperature"])
    apply_component_update(components.agentic, updates["agentic"])

# -----------------------------------------------------------------------------
async def handle_cloud_toggle(components: ClientComponents, event: Any) -> None:
    update = set_cloud_model_mode(bool(event.value))
    apply_component_update(components.openai_model, update)

# -----------------------------------------------------------------------------
async def handle_search_click(components: ClientComponents, event: Any) -> None:
    data, message = await submit_location_search(
        components.filter.value,
        sanitized_text(components.country.value),
        sanitized_text(components.city.value),
        sanitized_text(components.address.value),
        bool(components.use_coordinates.value),
        components.latitude.value,
        components.longitude.value,
        sanitized_text(components.date.value),
    )

    status_message = format_status_output(data, message or "Location search payload submitted.")
    apply_component_update(components.status, ComponentUpdate(value=status_message))


# MAIN UI PAGE
###############################################################################
def main_page() -> None:
    provider = ClientRuntimeConfig.get_llm_provider()
    cloud_models = CLOUD_MODEL_CHOICES.get(provider, [])
    selected_cloud_model = ClientRuntimeConfig.get_cloud_model()
    if selected_cloud_model not in cloud_models:
        selected_cloud_model = cloud_models[0] if cloud_models else ""
        ClientRuntimeConfig.set_cloud_model(selected_cloud_model)

    cloud_enabled = ClientRuntimeConfig.is_cloud_enabled()

    ui.page_title("AEGIS Geographics")
    ui.add_head_html(f"<style>{INTERFACE_THEME_CSS}</style>")
    #ui.add_css(INTERFACE_THEME_CSS)
   
    with ui.column().classes(PAGE_CONTAINER_CLASSES):
        ui.markdown("## AEGIS Geographics\nVisualize geographic data overlays in real time").classes(
            "text-3xl font-semibold text-slate-800 dark:text-slate-100"
        )
        with ui.row().classes("w-full flex-wrap justify-start"):
            with ui.card().classes("w-full max-w-md"):
                with ui.column().classes("gap-4"):
                    ui.markdown("**Authentication**")
                    auth_button = ui.button("Authenticate", on_click=None)
                    auth_button.props("color=secondary")
                    auth_button.props("size=sm")

        with ui.row().classes("w-full gap-6 items-start flex-wrap"):
            with ui.card().classes(
                "flex-1 min-w-[320px] w-full flex flex-col justify-between"
            ):
                with ui.column().classes("gap-4"):
                    ui.markdown("### Location search")
                    with ui.column().classes("gap-3"):
                        use_coordinates_switch = ui.switch("Provide latitude and longitude")
                        use_coordinates_switch.props("color=primary")

                        country_input = ui.input(
                            label="Country or Region",
                            placeholder="Enter a country or region",
                        )
                        country_input.classes("w-full")

                        city_input = ui.input(
                            label="City Name",
                            placeholder="Enter a city or locale",
                        )
                        city_input.classes("w-full")

                        address_input = ui.input(
                            label="Street Address",
                            placeholder="Enter the specific address",
                        )
                        address_input.classes("w-full")
                        address_input.props("required")

                        with ui.row().classes("w-full gap-3 flex-wrap"):
                            latitude_input = ui.number(
                                label="Latitude (°)",
                                format="%.6f",
                                step=0.000001,
                            )
                            latitude_input.classes("flex-1 min-w-[160px]")

                            longitude_input = ui.number(
                                label="Longitude (°)",
                                format="%.6f",
                                step=0.000001,
                            )
                            longitude_input.classes("flex-1 min-w-[160px]")

                        date_input = ui.input(label="Reference Moment")
                        date_input.props["type"] = "datetime-local"
                        date_input.set_value(get_datetime_default_value())

                        filter_select = ui.select(
                            FILTER_CHOICES,                            
                            label="Imagery Style",
                        )
                        filter_select.classes("w-full")

                    search_button = ui.button(
                        "Start search",
                        on_click=None,
                    )
                    search_button.props("color=primary")

            with ui.card().classes(
                "flex-1 min-w-[320px] w-full flex flex-col justify-between"
            ):
                with ui.column().classes("gap-3"):
                    ui.markdown("### Agentic Search")
                    agentic_checkbox = ui.checkbox("Activate agentic assistant")

                    llm_query_input = ui.textarea(
                        label="Agent Prompt",
                        placeholder="Describe the geographic insights you need",
                    )
                    llm_query_input.classes("w-full")

                    with ui.expansion("Model configuration", icon="settings"):
                        use_cloud_checkbox = ui.checkbox("Leverage OpenAI cloud models")
                        openai_model_dropdown = ui.select(
                            OPENAI_CLOUD_MODELS,
                            label="OpenAI model choice",
                        )
                        openai_model_dropdown.classes("w-full")
                        agent_model_dropdown = ui.select(
                            AGENT_MODEL_CHOICES,
                            value=ClientRuntimeConfig.set_agent_model,
                            label="Ollama agent model",
                        )
                        agent_model_dropdown.classes("w-full")

                        temperature_input = ui.number(
                                label="Temperature",
                                value=ClientRuntimeConfig.get_ollama_temperature(),
                                min=0.0,
                                max=2.0,
                                step=0.1,
                            ).classes("w-full")
                        reasoning_checkbox = ui.checkbox(
                                "Enable reasoning (think)",
                                value=ClientRuntimeConfig.is_ollama_reasoning_enabled(),
                            )

                agentic_button = ui.button("Run agentic search", on_click=None)
                agentic_button.props("color=secondary")

        with ui.row().classes(
            "w-full gap-4 items-stretch flex-wrap md:flex-nowrap"
        ):
            with ui.card().classes("flex-1 basis-[60%] min-w-[320px]"):
                with ui.column().classes("gap-3 h-full"):
                    ui.markdown("### Map Preview")
                    map_canvas = ui.image()
                    map_canvas.classes(
                        "w-full h-full min-h-[560px] max-h-[800px] object-contain bg-slate-100"
                    )

            with ui.card().classes(
                "basis-[40%] grow-0 min-w-[300px] max-w-[520px]"
            ):
                with ui.column().classes("gap-3 h-full"):
                    ui.markdown("### Endpoint Output")
                    with ui.scroll_area().classes(
                        "w-full h-full max-h-[640px]"
                    ):
                        status_display = ui.markdown(
                            "Adjust the parameters above, then fetch map imagery."
                        )
                        status_display.classes(
                            "text-sm whitespace-pre-wrap font-mono"
                        )

    components = ClientComponents(
        auth_button=auth_button,
        country=country_input,
        city=city_input,
        address=address_input,
        use_coordinates=use_coordinates_switch,
        latitude=latitude_input,
        longitude=longitude_input,
        date=date_input,
        filter=filter_select,
        search=search_button,
        agentic_toggle=agentic_checkbox,
        llm_query=llm_query_input,
        use_cloud=use_cloud_checkbox,
        openai_model=openai_model_dropdown,
        agent_model=agent_model_dropdown,
        temperature=temperature_input,
        agentic=agentic_button,
        status=status_display,
        map_display=map_canvas,
    )

    # Wire events (targeted updates)
    use_coordinates_switch.on_value_change(
        partial(handle_use_coordinates_change, components)
    )
    agentic_checkbox.on_value_change(
        partial(handle_agentic_toggle, components)
    )
    use_cloud_checkbox.on_value_change(
        partial(handle_cloud_toggle, components)
    )
    search_button.on_click(partial(handle_search_click, components))   


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
