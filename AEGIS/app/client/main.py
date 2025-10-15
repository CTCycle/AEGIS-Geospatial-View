from __future__ import annotations

from datetime import date
from typing import Final

import gradio as gr

from AEGIS.app.client.controllers import (
    adjust_timeline_slider,
    initiate_authentication,
    load_map_image,
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


def _default_timeline_bounds() -> tuple[int, int, int]:
    today = date.today()
    min_year = max(today.year - TIMELINE_DEFAULT_RANGE, 1900)
    max_year = today.year
    return min_year, max_year, today.year


###############################################################################
def create_interface() -> gr.Blocks:
    with gr.Blocks(
        title="AEGIS Geographics",
        analytics_enabled=False,
        theme="soft",
    ) as demo:
        gr.Markdown("# AEGIS Geographics\nVisualize geographic data overlays in real time.")

        with gr.Row():
            gr.Markdown("**Authentication**")
            auth_button = gr.Button(
                "Authenticate",
                variant="secondary",
                size="sm",
            )

        with gr.Row():
            with gr.Column(scale=1, min_width=360):
                with gr.Group():
                    gr.Markdown("### Imagery Parameters")
                    filter_dropdown = gr.Dropdown(
                        label="Filter",
                        choices=FILTER_CHOICES,
                        value=DEFAULT_FILTER,
                        interactive=True,
                    )
                    gr.Markdown("#### Location search")
                    country_dropdown = gr.Dropdown(
                        label="Country",
                        choices=COUNTRY_CHOICES,
                        value=None,
                        allow_custom_value=True,
                        interactive=True,
                    )
                    city_input = gr.Textbox(
                        label="City",
                        placeholder="Enter a city name",
                        lines=1,
                    )
                    use_coordinates_checkbox = gr.Checkbox(
                        label="Use coordinates instead",
                        value=False,
                    )
                    latitude_input = gr.Number(
                        label="Latitude",
                        value=None,
                        interactive=False,
                        precision=6,
                    )
                    longitude_input = gr.Number(
                        label="Longitude",
                        value=None,
                        interactive=False,
                        precision=6,
                    )
                    with gr.Row():
                        date_input = gr.Textbox(
                            label="Target date",
                            placeholder="YYYY-MM-DD",
                            lines=1,
                        )
                        time_input = gr.Textbox(
                            label="Day time",
                            placeholder="HH:MM",
                            lines=1,
                        )
                    load_button = gr.Button("Load imagery", variant="primary")
                    status_display = gr.Markdown(
                        value="Select parameters, then load imagery.",
                        visible=True,
                    )

            with gr.Column(scale=3):
                min_year, max_year, default_year = _default_timeline_bounds()
                timeline_slider = gr.Slider(
                    label="Timeline year",
                    minimum=min_year,
                    maximum=max_year,
                    value=default_year,
                    step=1,
                )
                map_canvas = gr.Image(
                    label="Geographic Canvas",
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

        load_button.click(
            fn=load_map_image,
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
