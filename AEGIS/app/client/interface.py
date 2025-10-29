from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Final

from nicegui import ui

from AEGIS.app.client.controllers import (
    NO_UPDATE,
    ComponentState,
    set_agentic_mode,
    set_cloud_model_mode,
    set_location_mode,
    submit_location_search,
)

FILTER_CHOICES: Final[list[str]] = [
    "Natural Color",
    "Topographic",
    "Population Density",
    "Weather Overlay",
]
DEFAULT_FILTER: Final[str] = FILTER_CHOICES[0]
OPENAI_MODEL_CHOICES: Final[list[str]] = [
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-3.5-turbo",
]
AGENT_MODEL_CHOICES: Final[list[str]] = [
    "llama3",
    "mistral",
    "phi3",
]
DEFAULT_AGENT_MODEL: Final[str] = AGENT_MODEL_CHOICES[0]
DEFAULT_AGENTIC_TEMPERATURE: Final[float] = 0.7

COMPONENTS: dict[str, Any] = {}


def get_component(name: str) -> Any | None:
    return COMPONENTS.get(name)


###############################################################################
def apply_component_state(name: str, state: ComponentState) -> None:
    component = get_component(name)
    if component is None:
        return
    if state.value is not NO_UPDATE:
        if hasattr(component, "set_value"):
            component.set_value(state.value)
        elif hasattr(component, "set_content"):
            component.set_content(state.value)
        else:
            component.value = state.value
    if state.enabled is not None:
        if state.enabled:
            component.enable()
        else:
            component.disable()
    if state.minimum is not None and hasattr(component, "props"):
        component.props["min"] = state.minimum
    if state.maximum is not None and hasattr(component, "props"):
        component.props["max"] = state.maximum
    component.update()


###############################################################################
def apply_component_states(states: dict[str, ComponentState]) -> None:
    for name, state in states.items():
        apply_component_state(name, state)


###############################################################################
def sanitized_text(value: Any) -> str | None:
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    return None






###############################################################################
def update_status_message(message: str) -> None:
    status_component = get_component("status")
    if status_component is None:
        return
    status_component.set_content(message)


###############################################################################
def get_datetime_default_value() -> str:
    current = datetime.now().replace(second=0, microsecond=0)
    return current.isoformat(timespec="minutes")

###############################################################################
def gather_search_parameters() -> dict[str, Any]:
    filter_component = get_component("filter")
    country_component = get_component("country")
    city_component = get_component("city")
    use_coordinates_component = get_component("use_coordinates")
    latitude_component = get_component("latitude")
    longitude_component = get_component("longitude")
    date_component = get_component("date")

    filter_value = filter_component.value if filter_component else None
    country_value = sanitized_text(country_component.value if country_component else None)
    city_value = sanitized_text(city_component.value if city_component else None)
    use_coordinates = bool(use_coordinates_component.value) if use_coordinates_component else False
    latitude_value = latitude_component.value if latitude_component else None
    longitude_value = longitude_component.value if longitude_component else None
    date_value = sanitized_text(date_component.value if date_component else None)

    coordinates = {
        "latitude": latitude_value if latitude_value is not None else None,
        "longitude": longitude_value if longitude_value is not None else None,
    }

    return {
        "filter": filter_value,
        "country": country_value,
        "city": city_value,
        "use_coordinates": use_coordinates,
        "coordinates": coordinates,
        "latitude": latitude_value,
        "longitude": longitude_value,
        "datetime": date_value,
        "date": date_value,
    }


###############################################################################
async def handle_search_click() -> None:
    parameters = gather_search_parameters()
    data, message = await submit_location_search(parameters)
    status_message = message or "Location search payload submitted."
    if isinstance(data, dict):
        payload = data.get("payload")
        if isinstance(payload, dict):
            serialized = json.dumps(payload, indent=2, sort_keys=True)
            status_message = f"{status_message}\n\n```json\n{serialized}\n```"
    update_status_message(status_message)
  





###############################################################################
def configure_interface() -> None:
    COMPONENTS.clear()
    ui.page_title("AEGIS Geographics")
    ui.markdown("# AEGIS Geographics\nVisualize geographic data overlays in real time.")

    with ui.column().classes("w-full gap-8"):
        with ui.row().classes("w-full flex-wrap justify-start"):
            with ui.card().classes("w-full max-w-md"):
                with ui.column().classes("gap-4"):
                    ui.markdown("**Authentication**")
                    auth_button = ui.button(
                        "Authenticate", on_click=None
                    )
                    auth_button.props("color=secondary")
                    auth_button.props("size=sm")
                    COMPONENTS["auth_button"] = auth_button

        with ui.row().classes("w-full gap-6 items-start flex-wrap"):
            with ui.card().classes("flex-1 min-w-[320px]"):
                with ui.column().classes("gap-3"):
                    ui.markdown("### Location search")
                    filter_select = ui.select(
                        FILTER_CHOICES,
                        value=DEFAULT_FILTER,
                        label="Imagery Style",
                    )
                    filter_select.classes("w-full")
                    COMPONENTS["filter"] = filter_select

                    country_input = ui.input(
                        label="Country or Region",
                        placeholder="Enter a country or region",
                    )
                    country_input.classes("w-full")
                    COMPONENTS["country"] = country_input

                    city_input = ui.input(
                        label="City Name",
                        placeholder="Enter a city or locale",
                    )
                    city_input.classes("w-full")
                    COMPONENTS["city"] = city_input

                    use_coordinates_checkbox = ui.checkbox("Provide precise coordinates")
                    COMPONENTS["use_coordinates"] = use_coordinates_checkbox

                    latitude_input = ui.number(
                        label="Latitude (°)",
                        format="%.6f",
                        step=0.000001,
                    )
                    COMPONENTS["latitude"] = latitude_input

                    longitude_input = ui.number(
                        label="Longitude (°)",
                        format="%.6f",
                        step=0.000001,
                    )
                    COMPONENTS["longitude"] = longitude_input

                    date_input = ui.input(label="Reference Moment")
                    date_input.props["type"] = "datetime-local"
                    date_input.set_value(get_datetime_default_value())
                    COMPONENTS["date"] = date_input

                    search_button = ui.button(
                        "Search Imagery", on_click=handle_search_click
                    )
                    search_button.props("color=primary")
                    COMPONENTS["search"] = search_button

            with ui.card().classes("flex-1 min-w-[320px]"):
                with ui.column().classes("gap-3"):
                    ui.markdown("### Agentic Search")
                    agentic_checkbox = ui.checkbox("Activate agentic assistant")
                    COMPONENTS["agentic_toggle"] = agentic_checkbox

                    llm_query_input = ui.textarea(
                        label="Agent Prompt",
                        placeholder="Describe the geographic insights you need",
                    )
                    llm_query_input.classes("w-full")
                    COMPONENTS["llm_query"] = llm_query_input

                    with ui.expansion("Model configuration", icon="settings"):
                        use_cloud_checkbox = ui.checkbox("Leverage OpenAI cloud models")
                        COMPONENTS["use_cloud"] = use_cloud_checkbox

                        openai_model_dropdown = ui.select(
                            OPENAI_MODEL_CHOICES,
                            label="OpenAI model choice",
                        )
                        openai_model_dropdown.classes("w-full")
                        COMPONENTS["openai_model"] = openai_model_dropdown

                        agent_model_dropdown = ui.select(
                            AGENT_MODEL_CHOICES,
                            value=DEFAULT_AGENT_MODEL,
                            label="Ollama agent model",
                        )
                        agent_model_dropdown.classes("w-full")
                        COMPONENTS["agent_model"] = agent_model_dropdown

                        temperature_input = ui.number(
                            label="Sampling temperature",
                            value=DEFAULT_AGENTIC_TEMPERATURE,
                            step=0.1,
                            format="%.2f",
                        )
                        COMPONENTS["temperature"] = temperature_input

                    agentic_button = ui.button("Run agentic search", on_click=None)
                    agentic_button.props("color=secondary")
                    COMPONENTS["agentic"] = agentic_button

                    status_display = ui.markdown(
                        "Adjust the parameters above, then fetch map imagery."
                    )
                    COMPONENTS["status"] = status_display

        with ui.row().classes("w-full items-stretch"):
            with ui.card().classes("w-full"):
                with ui.column().classes("gap-3"):
                    ui.markdown("### Map Preview")

                    map_canvas = ui.image()
                    map_canvas.classes(
                        "w-full min-h-[360px] max-h-[640px] object-contain bg-slate-100"
                    )
                    COMPONENTS["map"] = map_canvas
    
    apply_component_states(set_location_mode(False))
    apply_component_states(set_agentic_mode(False, False))
    apply_component_state("openai_model", set_cloud_model_mode(False))
    update_status_message("Adjust the parameters above, then fetch map imagery.")


###############################################################################
@ui.page("/")
def render_interface_page() -> None:
    configure_interface()


###############################################################################
def create_interface() -> None:
    # kept for compatibility: page registration happens via decorator
    pass


###############################################################################
def launch_interface() -> None:
    create_interface()
    ui.run(host="127.0.0.1", port=7861, title="AEGIS Geographics", reload=False)


if __name__ == "__main__":
    launch_interface()
