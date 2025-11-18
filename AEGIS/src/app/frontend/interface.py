from __future__ import annotations

import json
from datetime import datetime
from functools import partial
from typing import Any

from nicegui import ui

from AEGIS.src.app.frontend.controllers import (
    GeoSearchController,
    SettingsController,
)
from AEGIS.src.app.frontend.layouts import (
    CARD_BASE_CLASSES,
    INTERFACE_THEME_CSS,
    PAGE_CONTAINER_CLASSES,
)
from AEGIS.src.packages.configurations import configurations
from AEGIS.src.packages.constants import (
    AGENT_MODEL_CHOICES,
    CLOUD_MODEL_CHOICES,
    GEOSPATIAL_LAYER_CHOICES,
)

CLOUD_PROVIDERS: list[str] = [key for key in CLOUD_MODEL_CHOICES]
UI_RUNTIME = configurations.ui_runtime


###############################################################################
class InterfaceToolkit:
    def get_datetime_default_value(self) -> str:
        current = datetime.now().replace(second=0, microsecond=0)
        return current.isoformat(timespec="minutes")

    def update_status_with_json(
        self, status_display: Any, message: str, payload: Any
    ) -> None:
        parts: list[str] = []
        if message:
            parts.append(message.strip())
        if payload is not None:
            formatted = json.dumps(payload, indent=2, sort_keys=True, default=str)
            parts.append(f"```json\n{formatted}\n```")
        content = "\n\n".join(parts) if parts else "Waiting for response..."
        status_display.set_content(content)

    def resolve_map_image_source(self, response: Any) -> str | None:
        if not isinstance(response, dict):
            return None
        payload = response.get("payload")
        if not isinstance(payload, dict):
            return None
        imagery = payload.get("satellite_imagery")
        if not isinstance(imagery, dict):
            return None
        encoded = str(imagery.get("image_base64") or "").strip()
        normalized_payload = encoded.replace("\n", "").replace("\r", "")
        if normalized_payload:
            mime_candidate = str(
                imagery.get("mime") or imagery.get("format") or "image/png"
            )
            normalized_mime = mime_candidate.strip().lower()
            if not normalized_mime.startswith("image/"):
                normalized_mime = f"image/{normalized_mime.split('/')[-1]}"
            return f"data:{normalized_mime};base64,{normalized_payload}"
        direct_source = str(
            imagery.get("image_url") or imagery.get("wms_url") or ""
        ).strip()
        if direct_source:
            return direct_source
        return None

    def update_map_canvas(self, map_canvas: Any, response: Any) -> None:
        if map_canvas is None:
            return
        source = self.resolve_map_image_source(response)
        if not source:
            map_canvas.set_source("")
            return
        if getattr(map_canvas, "source", None) == source:
            return
        map_canvas.set_source(source)

    def normalize_filter_candidate(self, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized or normalized.lower() == "none":
            return None
        return normalized


###############################################################################
class InterfaceController:
    def __init__(
        self,
        settings_controller: SettingsController,
        geo_search_controller: GeoSearchController,
        toolkit: InterfaceToolkit,
    ):
        self.settings_controller = settings_controller
        self.geo_search_controller = geo_search_controller
        self.toolkit = toolkit

    async def handle_toggle_cloud_services(
        self,
        llm_provider_dropdown: Any,
        cloud_model_dropdown: Any,
        agent_model_dropdown: Any,
        temperature_input: Any,
        reasoning_checkbox: Any,
        event: Any,
    ) -> None:
        enabled = bool(event.value)
        selection = self.settings_controller.resolve_cloud_selection(
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

    async def handle_cloud_provider_change(
        self,
        llm_provider_dropdown: Any,
        cloud_model_dropdown: Any,
        event: Any,
    ) -> None:
        selection = self.settings_controller.resolve_cloud_selection(
            str(event.value or ""),
            str(cloud_model_dropdown.value or ""),
        )
        llm_provider_dropdown.value = selection["provider"]
        llm_provider_dropdown.update()
        cloud_model_dropdown.set_options(selection["models"])
        cloud_model_dropdown.value = selection["model"]
        cloud_model_dropdown.update()

    async def on_use_coordinates_change(
        self,
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

    # -------------------------------------------------------------------------
    def refresh_geospatial_chips(
        self,
        chip_container: Any,
        selected_filters: list[str],
        geospatial_select: Any,
    ) -> None:
        chip_container.clear()
        with chip_container:
            if not selected_filters:
                ui.label("No filters selected").classes("text-sm text-gray-500")
                return
            for filter_value in selected_filters:
                ui.chip(
                    filter_value,
                    on_click=partial(
                        self.on_remove_geospatial_filter,
                        filter_value=filter_value,
                        selected_filters=selected_filters,
                        chip_container=chip_container,
                        geospatial_select=geospatial_select,
                    ),
                ).props("color=primary outline clickable")

    # -------------------------------------------------------------------------
    def on_geospatial_filter_select(
        self,
        event: Any,
        *,
        selected_filters: list[str],
        chip_container: Any,
        geospatial_select: Any,
    ) -> None:
        candidate = getattr(event, "value", event)
        normalized = self.toolkit.normalize_filter_candidate(candidate)
        geospatial_select.value = None
        geospatial_select.update()
        if normalized is None or normalized in selected_filters:
            return
        selected_filters.append(normalized)
        self.refresh_geospatial_chips(
            chip_container=chip_container,
            selected_filters=selected_filters,
            geospatial_select=geospatial_select,
        )

    # -------------------------------------------------------------------------
    def on_remove_geospatial_filter(
        self,
        event: Any,
        *,
        filter_value: str,
        selected_filters: list[str],
        chip_container: Any,
        geospatial_select: Any,
    ) -> None:
        filtered = [value for value in selected_filters if value != filter_value]
        selected_filters[:] = filtered
        geospatial_select.update()
        self.refresh_geospatial_chips(
            chip_container=chip_container,
            selected_filters=selected_filters,
            geospatial_select=geospatial_select,
        )

    async def on_search_click(
        self,
        event: Any,
        *,
        geospatial_filters: list[str],
        country_input: Any,
        city_input: Any,
        address_input: Any,
        use_coordinates_switch: Any,
        latitude_input: Any,
        longitude_input: Any,
        date_input: Any,
        agentic_checkbox: Any,
        status_display: Any,
        map_canvas: Any,
    ) -> None:
        result = await self.geo_search_controller.submit_location_search(
            geospatial_filters,
            country_input.value,
            city_input.value,
            address_input.value,
            use_coordinates_switch.value,
            latitude_input.value,
            longitude_input.value,
            date_input.value,
            bool(agentic_checkbox.value),
        )
        message = result.get("message") or "Location search payload submitted."
        self.toolkit.update_status_with_json(
            status_display, message, result.get("json")
        )
        self.toolkit.update_map_canvas(map_canvas, result.get("json"))

    # -------------------------------------------------------------------------
    def on_agent_prompt_toggle(
        self,
        event: Any,
        *,
        agent_prompt_accordion: Any,
        agent_prompt_input: Any,
    ) -> None:
        is_enabled = bool(getattr(event, "value", event))
        agent_prompt_accordion.set_value(is_enabled)
        if is_enabled:
            agent_prompt_input.enable()
        else:
            agent_prompt_input.value = ""
            agent_prompt_input.disable()


###############################################################################
class InterfaceStructure:
    def __init__(
        self,
        controller: InterfaceController,
        settings_controller: SettingsController,
        toolkit: InterfaceToolkit,
    ):
        self.controller = controller
        self.settings_controller = settings_controller
        self.toolkit = toolkit

    def main_page(self) -> None:
        current_settings = self.settings_controller.get_runtime_settings()
        selection = self.settings_controller.resolve_cloud_selection(
            current_settings.provider, current_settings.cloud_model
        )
        provider = selection["provider"]
        cloud_models = selection["models"]
        selected_cloud_model = selection["model"]
        cloud_enabled = current_settings.use_cloud_services

        ui.page_title("AEGIS Geographics")
        ui.add_head_html(f"<style>{INTERFACE_THEME_CSS}</style>")

        config_toolbar = ui.left_drawer(value=False, fixed=True).props(
            "width=320 elevated overlay bordered"
        )
        with config_toolbar:
            with ui.column().classes("gap-4 p-4"):
                ui.label("Models Configuration").classes("aegis-card-title")
                ui.label("Configuration").classes("aegis-subtitle")
                use_cloud_services = ui.checkbox(
                    "Use Cloud Services",
                    value=cloud_enabled,
                )
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
                        ui.label("Ollama Configuration").classes("aegis-subtitle")
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
            ui.button(
                icon="chevron_left",
                on_click=lambda _: config_toolbar.set_value(False),
            ).props("flat color=primary").classes("self-start mt-auto mb-2 no-outline")

        ui.element("div").classes(
            "fixed left-0 top-40 z-40 bg-primary cursor-pointer "
            "rounded-r-lg opacity-70 hover:opacity-100 transition-all duration-300"
        ).style("width:16px; height:120px;").on(
            "click",
            lambda _: config_toolbar.set_value(True),
        )

        with ui.column().classes(PAGE_CONTAINER_CLASSES):
            ui.markdown(
                "### AEGIS Geographics\nVisualize geographic data overlays in real time"
            ).classes("text-3xl font-semibold text-slate-800 dark:text-slate-100")
            with ui.row().classes("w-full flex-wrap justify-start"):
                with ui.card().classes(f"{CARD_BASE_CLASSES} w-full"):
                    with ui.column().classes("gap-4"):
                        ui.markdown("**Authentication**")
                        auth_button = ui.button("Authenticate", on_click=None)
                        auth_button.props("color=secondary")
                        auth_button.props("size=sm")

            with ui.row().classes(
                "w-full gap-6 items-start flex-wrap xl:flex-nowrap"
            ):
                with ui.card().classes(
                    f"{CARD_BASE_CLASSES} flex-1 w-full min-w-[420px]"
                ):
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
                                    label="Latitude (?)",
                                    format="%.6f",
                                    step=0.000001,
                                ).classes("flex-1 min-w-[160px]")
                                latitude_input.disable()
                                longitude_input = ui.number(
                                    label="Longitude (?)",
                                    format="%.6f",
                                    step=0.000001,
                                ).classes("flex-1 min-w-[160px]")
                                longitude_input.disable()

                            date_input = ui.input(label="Reference Moment")
                            date_input.props["type"] = "datetime-local"
                            date_input.set_value(
                                self.toolkit.get_datetime_default_value()
                            )

                            geospatial_filter_options = [
                                *GEOSPATIAL_LAYER_CHOICES,
                            ]
                            geospatial_selected_filters: list[str] = []
                            geospatial_select = ui.select(
                                geospatial_filter_options,
                                label="Geospatial Filter",
                                value=None,
                            ).classes("w-full")
                            geospatial_chip_container = (
                                ui.row()
                                .classes("w-full gap-2 flex-wrap")
                                .style("min-height: 32px;")
                            )
                            self.controller.refresh_geospatial_chips(
                                chip_container=geospatial_chip_container,
                                selected_filters=geospatial_selected_filters,
                                geospatial_select=geospatial_select,
                            )
                            ui.separator().classes("w-full opacity-60")

                        ui.space()
                        ui.separator().classes("w-full opacity-60")                        
                        agentic_expansion = ui.expansion(
                            "", value=False
                        ).classes("w-full")
                        with agentic_expansion:
                            with agentic_expansion.add_slot("header"):
                                with ui.row().classes("items-center gap-2"):
                                    agentic_checkbox = ui.checkbox(
                                        "Activate agentic assistant",
                                        value=False,
                                    )
                                    
                            llm_query_input = ui.textarea(
                                label="Agent Prompt",
                                placeholder="Describe the geographic insights you need",
                            ).classes("w-full")
                            llm_query_input.disable()
                        agentic_checkbox.on_value_change(
                            lambda e: (
                                (
                                    agentic_expansion.set_value(True),
                                    llm_query_input.enable(),
                                )
                                if bool(getattr(e, "value", False))
                                else (
                                    agentic_expansion.set_value(False),
                                    llm_query_input.disable(),
                                )
                            )
                        )

                        ui.space()
                        search_button = ui.button(
                            "Run search",
                            on_click=None,
                        ).props("color=primary size=lg").classes("w-full")

                with ui.column().classes(
                    "flex-1 min-w-[360px] gap-4 w-full xl:w-1/2"
                ):
                    with ui.card().classes(
                        f"{CARD_BASE_CLASSES} flex-1 min-w-0 w-full"
                    ):
                        with ui.column().classes("gap-3 h-full w-full items-stretch"):
                            ui.markdown("#### Map Preview")
                            map_canvas = ui.image()
                            map_canvas.classes(
                                "w-full h-full min-h-[480px] max-h-[800px] "
                                "object-contain bg-slate-100 rounded-lg aspect-square"
                            )

                    with ui.card().classes(
                        f"{CARD_BASE_CLASSES} flex-1 min-w-0 w-full"
                    ):
                        with ui.column().classes("gap-3 h-full w-full items-stretch"):
                            output_accordion = ui.expansion(
                                "Endpoint Output",
                                value=False,
                            ).classes("w-full")
                            with output_accordion:
                                with ui.scroll_area().classes(
                                    "w-full h-full max-h-[360px] min-w-0 grow rounded-lg"
                                ):
                                    status_display = ui.markdown(
                                        "Waiting for response..."
                                    )
                                    status_display.classes(
                                        "status-output w-full text-sm font-mono"
                                    )

        use_cloud_services.on_value_change(
            partial(
                self.controller.handle_toggle_cloud_services,
                llm_provider_dropdown,
                cloud_model_dropdown,
                agent_model_dropdown,
                temperature_input,
                reasoning_checkbox,
            )
        )
        llm_provider_dropdown.on_value_change(
            partial(
                self.controller.handle_cloud_provider_change,
                llm_provider_dropdown,
                cloud_model_dropdown,
            )
        )
        geospatial_select.on_value_change(
            partial(
                self.controller.on_geospatial_filter_select,
                selected_filters=geospatial_selected_filters,
                chip_container=geospatial_chip_container,
                geospatial_select=geospatial_select,
            )
        )
        use_coordinates_switch.on_value_change(
            partial(
                self.controller.on_use_coordinates_change,
                country_input=country_input,
                city_input=city_input,
                address_input=address_input,
                latitude_input=latitude_input,
                longitude_input=longitude_input,
            )
        )
        search_button.on_click(
            partial(
                self.controller.on_search_click,
                geospatial_filters=geospatial_selected_filters,
                country_input=country_input,
                city_input=city_input,
                address_input=address_input,
                use_coordinates_switch=use_coordinates_switch,
                latitude_input=latitude_input,
                longitude_input=longitude_input,
                date_input=date_input,
                agentic_checkbox=agentic_checkbox,
                status_display=status_display,
                map_canvas=map_canvas,
            )
        )


###############################################################################
def create_interface() -> None:
    toolkit = InterfaceToolkit()
    settings_controller = SettingsController()
    geo_search_controller = GeoSearchController()
    controller = InterfaceController(
        settings_controller=settings_controller,
        geo_search_controller=geo_search_controller,
        toolkit=toolkit,
    )
    structure = InterfaceStructure(
        controller=controller,
        settings_controller=settings_controller,
        toolkit=toolkit,
    )
    ui.page("/")(structure.main_page)


# -----------------------------------------------------------------------------
def launch_interface() -> None:
    create_interface()
    ui.run(
        host=UI_RUNTIME.host,
        port=UI_RUNTIME.port,
        title=UI_RUNTIME.title,
        show_welcome_message=UI_RUNTIME.show_welcome_message,
    )


# -----------------------------------------------------------------------------
if __name__ in {"__main__", "__mp_main__"}:
    launch_interface()
