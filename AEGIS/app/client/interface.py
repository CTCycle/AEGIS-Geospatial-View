from __future__ import annotations

import base64
from binascii import Error as BinasciiError
from datetime import date, datetime
from typing import Any, Final

from nicegui import events, ui

from AEGIS.app.client.controllers import (
    NO_UPDATE,
    ComponentState,
    adjust_timeline_slider,
    load_agentic_map_image,
    load_default_map_image,
    set_agentic_mode,
    set_cloud_model_mode,
    set_location_mode,
)

FILTER_CHOICES: Final[list[str]] = [
    "Natural Color",
    "Topographic",
    "Population Density",
    "Weather Overlay",
]
COUNTRY_CHOICES: Final[list[str]] = [
    "Italy",
    "United States",
    "United Kingdom",
    "Canada",
    "Australia",
]
DEFAULT_FILTER: Final[str] = FILTER_CHOICES[0]
TIMELINE_DEFAULT_RANGE: Final[int] = 20
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


###############################################################################
def default_timeline_bounds() -> tuple[int, int, int]:
    today = date.today()
    min_year = max(today.year - TIMELINE_DEFAULT_RANGE, 1900)
    max_year = today.year
    return min_year, max_year, today.year


###############################################################################
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
def encode_image_source(image_data: bytes | str | None) -> str | None:
    if image_data is None:
        return None
    if isinstance(image_data, bytes):
        encoded = base64.b64encode(image_data).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    candidate = image_data.strip()
    if not candidate:
        return None
    if candidate.startswith("data:") or candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    try:
        base64.b64decode(candidate, validate=True)
    except (ValueError, BinasciiError):
        return candidate
    return f"data:image/png;base64,{candidate}"


###############################################################################
def update_map_image(image_data: bytes | str | None) -> None:
    image_component = get_component("map")
    if image_component is None:
        return
    source = encode_image_source(image_data)
    if source is None:
        image_component.set_source("")
    else:
        image_component.set_source(source)


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
async def handle_use_coordinates_change(event: events.ValueChangeEvent) -> None:
    states = set_location_mode(bool(event.value))
    apply_component_states(states)


###############################################################################
async def handle_agentic_toggle(event: events.ValueChangeEvent) -> None:
    agentic_enabled = bool(event.value)
    use_coordinates_component = get_component("use_coordinates")
    use_coordinates = bool(use_coordinates_component.value) if use_coordinates_component else False
    states = set_agentic_mode(agentic_enabled, use_coordinates)
    apply_component_states(states)


###############################################################################
async def handle_cloud_models_change(event: events.ValueChangeEvent) -> None:
    state = set_cloud_model_mode(bool(event.value))
    apply_component_state("openai_model", state)


###############################################################################
def handle_date_change(event: events.ValueChangeEvent) -> None:
    state = adjust_timeline_slider(event.value)
    apply_component_state("timeline", state)


###############################################################################
def gather_search_parameters() -> dict[str, Any]:
    filter_component = get_component("filter")
    country_component = get_component("country")
    city_component = get_component("city")
    use_coordinates_component = get_component("use_coordinates")
    latitude_component = get_component("latitude")
    longitude_component = get_component("longitude")
    date_component = get_component("date")
    timeline_component = get_component("timeline")

    filter_value = filter_component.value if filter_component else None
    country_value = sanitized_text(country_component.value if country_component else None)
    city_value = sanitized_text(city_component.value if city_component else None)
    use_coordinates = bool(use_coordinates_component.value) if use_coordinates_component else False
    latitude_value = latitude_component.value if latitude_component else None
    longitude_value = longitude_component.value if longitude_component else None
    date_value = date_component.value if date_component else None
    timeline_value = timeline_component.value if timeline_component else None

    return {
        "filter": filter_value,
        "country": country_value,
        "city": city_value,
        "use_coordinates": use_coordinates,
        "latitude": latitude_value,
        "longitude": longitude_value,
        "date": date_value,
        "timeline": timeline_value,
    }


###############################################################################
def gather_agentic_parameters() -> dict[str, Any]:
    llm_query_component = get_component("llm_query")
    use_cloud_component = get_component("use_cloud")
    openai_model_component = get_component("openai_model")
    agent_model_component = get_component("agent_model")
    temperature_component = get_component("temperature")

    llm_query_value = llm_query_component.value if llm_query_component else None
    use_cloud_models = bool(use_cloud_component.value) if use_cloud_component else False
    openai_model_value = openai_model_component.value if openai_model_component else None
    agent_model_value = agent_model_component.value if agent_model_component else None
    temperature_value = temperature_component.value if temperature_component else None

    return {
        "llm_query": llm_query_value,
        "use_cloud_models": use_cloud_models,
        "openai_model": openai_model_value,
        "agent_model": agent_model_value,
        "temperature": temperature_value,
    }


###############################################################################
async def handle_search_click() -> None:
    parameters = gather_search_parameters()
    image_data, message = await load_default_map_image(
        filter_name=parameters["filter"],
        country=parameters["country"],
        city=parameters["city"],
        use_coordinates=parameters["use_coordinates"],
        latitude=parameters["latitude"],
        longitude=parameters["longitude"],
        target_moment=parameters["date"],
        timeline_year=parameters["timeline"],
    )
    update_map_image(image_data)
    update_status_message(message)


###############################################################################
async def handle_agentic_click() -> None:
    parameters = gather_agentic_parameters()
    image_data, message = await load_agentic_map_image(
        llm_query=parameters["llm_query"],
        use_cloud_models=parameters["use_cloud_models"],
        openai_model=parameters["openai_model"],
        agent_model=parameters["agent_model"],
        temperature=parameters["temperature"],
    )
    update_map_image(image_data)
    update_status_message(message)


###############################################################################
def handle_authenticate_click() -> None:
    message = initiate_authentication()
    update_status_message(message)


###############################################################################
def configure_interface() -> None:
    COMPONENTS.clear()
    ui.page_title("AEGIS Geographics")
    ui.markdown("# AEGIS Geographics\nVisualize geographic data overlays in real time.")

    with ui.row().classes("w-full gap-8 flex-wrap"):
        with ui.column().classes("max-w-md gap-4"):
            ui.markdown("**Authentication**")
            auth_button = ui.button("Authenticate", on_click=handle_authenticate_click)
            auth_button.props("color=secondary")
            auth_button.props("size=sm")
            COMPONENTS["auth_button"] = auth_button

        with ui.column().classes("max-w-2xl gap-4"):
            with ui.row().classes("w-full gap-6 flex-wrap"):
                with ui.column().classes("min-w-[320px] max-w-md gap-3"):
                    ui.markdown("### Location search")
                    filter_select = ui.select(
                        FILTER_CHOICES,
                        value=DEFAULT_FILTER,
                        label="Imagery Style",
                    )
                    filter_select.classes("w-full")
                    COMPONENTS["filter"] = filter_select

                    country_select = ui.select(
                        COUNTRY_CHOICES,
                        label="Country or Region",
                        with_input=True,
                    )
                    country_select.classes("w-full")
                    COMPONENTS["country"] = country_select

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

                    search_button = ui.button("Search Imagery", on_click=handle_search_click)
                    search_button.props("color=primary")
                    COMPONENTS["search"] = search_button

                with ui.column().classes("min-w-[320px] max-w-md gap-3"):
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

                    agentic_button = ui.button("Run agentic search", on_click=handle_agentic_click)
                    agentic_button.props("color=secondary")
                    COMPONENTS["agentic"] = agentic_button

                    status_display = ui.markdown(
                        "Adjust the parameters above, then fetch map imagery."
                    )
                    COMPONENTS["status"] = status_display

            with ui.column().classes("min-w-[360px] flex-1 gap-3"):
                ui.markdown("### Historical Timeline")
                min_year, max_year, default_year = default_timeline_bounds()
                timeline_slider = ui.slider(min=min_year, max=max_year, step=1)
                timeline_slider.set_value(default_year)
                COMPONENTS["timeline"] = timeline_slider

                map_canvas = ui.image()
                map_canvas.classes("w-full max-h-[512px] object-contain bg-slate-100")
                COMPONENTS["map"] = map_canvas

    use_coordinates_checkbox.on_value_change(handle_use_coordinates_change)
    agentic_checkbox.on_value_change(handle_agentic_toggle)
    use_cloud_checkbox.on_value_change(handle_cloud_models_change)
    date_input.on_value_change(handle_date_change)

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
    return None


###############################################################################
def launch_interface() -> None:
    create_interface()
    ui.run(host="127.0.0.1", port=7861, title="AEGIS Geographics", reload=False)


if __name__ == "__main__":
    launch_interface()
