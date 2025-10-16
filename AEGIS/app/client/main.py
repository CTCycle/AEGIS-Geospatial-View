from __future__ import annotations

from datetime import date
from typing import Final

import gradio as gr

from AEGIS.app.client.controllers import (
    adjust_timeline_slider,
    initiate_authentication,
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
GREEN_THEME: Final = gr.themes.Soft(
    primary_hue="emerald",
    secondary_hue="green",
    neutral_hue="slate",
)


def default_timeline_bounds() -> tuple[int, int, int]:
    today = date.today()
    min_year = max(today.year - TIMELINE_DEFAULT_RANGE, 1900)
    max_year = today.year
    return min_year, max_year, today.year


###############################################################################
def create_interface() -> gr.Blocks:
    with gr.Blocks(
        title="AEGIS Geographics",
        analytics_enabled=False,
        theme=GREEN_THEME,
    ) as demo:
        gr.Markdown("# AEGIS Geographics\nVisualize geographic data overlays in real time.")

        with gr.Row():
            with gr.Column(scale=1, min_width=240):
                gr.Markdown("**Authentication**")
                auth_button = gr.Button(
                    "Authenticate",
                    variant="secondary",
                    size="sm",
                )

        with gr.Row():
            with gr.Column(scale=1, min_width=360):
                with gr.Box():
                    gr.Markdown("### Location search")
                    filter_dropdown = gr.Dropdown(
                        label="Imagery Style",
                        choices=FILTER_CHOICES,
                        value=DEFAULT_FILTER,
                        interactive=True,
                    )
                    country_dropdown = gr.Dropdown(
                        label="Country or Region",
                        choices=COUNTRY_CHOICES,
                        value=None,
                        allow_custom_value=True,
                        interactive=True,
                    )
                    city_input = gr.Textbox(
                        label="City Name",
                        placeholder="Enter a city or locale",
                        lines=1,
                    )
                    use_coordinates_checkbox = gr.Checkbox(
                        label="Provide precise coordinates",
                        value=False,
                    )
                    latitude_input = gr.Number(
                        label="Latitude (°)",
                        value=None,
                        interactive=False,
                        precision=6,
                    )
                    longitude_input = gr.Number(
                        label="Longitude (°)",
                        value=None,
                        interactive=False,
                        precision=6,
                    )
                    with gr.Row():
                        date_input = gr.Textbox(
                            label="Reference Date",
                            placeholder="YYYY-MM-DD",
                            lines=1,
                        )
                        time_input = gr.Textbox(
                            label="Local Time",
                            placeholder="HH:MM",
                            lines=1,
                        )
                    search_button = gr.Button(
                        "Search Imagery",
                        variant="primary",
                    )

                with gr.Group():
                    gr.Markdown("### Agentic Search")
                    agentic_search_checkbox = gr.Checkbox(
                        label="Activate agentic assistant",
                        value=False,
                    )
                    llm_query_input = gr.Textbox(
                        label="Agent Prompt",
                        placeholder="Describe the geographic insights you need",
                        lines=4,
                        interactive=False,
                    )
                    with gr.Accordion("Model configuration", open=False):
                        use_cloud_models_checkbox = gr.Checkbox(
                            label="Leverage OpenAI cloud models",
                            value=False,
                            interactive=False,
                        )
                        openai_model_dropdown = gr.Dropdown(
                            label="OpenAI model choice",
                            choices=OPENAI_MODEL_CHOICES,
                            value=None,
                            allow_custom_value=False,
                            interactive=False,
                        )
                        with gr.Group():
                            agent_model_selector = gr.Dropdown(
                                label="Ollama agent model",
                                choices=AGENT_MODEL_CHOICES,
                                value=DEFAULT_AGENT_MODEL,
                                interactive=False,
                            )
                        temperature_input = gr.Number(
                            label="Sampling temperature",
                            value=DEFAULT_AGENTIC_TEMPERATURE,
                            interactive=False,
                            precision=2,
                        )

                    agentic_button = gr.Button(
                        "Run agentic search",
                        variant="secondary",
                        interactive=False,
                    )
                status_display = gr.Markdown(
                    value="Adjust the parameters above, then fetch map imagery.",
                    visible=True,
                )

            with gr.Column(scale=3):
                min_year, max_year, default_year = default_timeline_bounds()
                timeline_slider = gr.Slider(
                    label="Historical Timeline",
                    minimum=min_year,
                    maximum=max_year,
                    value=default_year,
                    step=1,
                )
                map_canvas = gr.Image(
                    label="Map Preview",
                    height=512,
                    show_download_button=True,
                )

        use_coordinates_checkbox.change(
            fn=set_location_mode,
            inputs=use_coordinates_checkbox,
            outputs=[
                country_dropdown,
                city_input,
                latitude_input,
                longitude_input,
            ],
        )

        auth_button.click(
            fn=initiate_authentication,
            outputs=status_display,
        )

        date_input.change(
            fn=adjust_timeline_slider,
            inputs=date_input,
            outputs=timeline_slider,
        )

        agentic_search_checkbox.change(
            fn=set_agentic_mode,
            inputs=[agentic_search_checkbox, use_coordinates_checkbox],
            outputs=[
                filter_dropdown,
                country_dropdown,
                city_input,
                use_coordinates_checkbox,
                latitude_input,
                longitude_input,
                date_input,
                time_input,
                timeline_slider,
                llm_query_input,
                use_cloud_models_checkbox,
                openai_model_dropdown,
                agent_model_selector,
                temperature_input,
                search_button,
                agentic_button,
            ],
        )

        use_cloud_models_checkbox.change(
            fn=set_cloud_model_mode,
            inputs=use_cloud_models_checkbox,
            outputs=openai_model_dropdown,
        )

        search_button.click(
            fn=load_default_map_image,
            inputs=[
                filter_dropdown,
                country_dropdown,
                city_input,
                use_coordinates_checkbox,
                latitude_input,
                longitude_input,
                date_input,
                time_input,
                timeline_slider,
            ],
            outputs=[map_canvas, status_display],
        )

        agentic_button.click(
            fn=load_agentic_map_image,
            inputs=[
                llm_query_input,
                use_cloud_models_checkbox,
                openai_model_dropdown,
                agent_model_selector,
                temperature_input,
            ],
            outputs=[map_canvas, status_display],
        )

    return demo


###############################################################################
def launch_interface() -> None:
    create_interface().queue(max_size=32).launch(
        server_name="127.0.0.1",
        server_port=7861,
        inbrowser=True,
    )


if __name__ == "__main__":
    launch_interface()
