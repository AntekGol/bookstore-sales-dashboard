from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def render_dashboard(store_results, api_url=""):
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )
    template = environment.get_template("dashboard.html")

    chart_data = {}
    store_summaries = []
    for store in store_results:
        chart_data[store["store"]] = [[row["date"], row["revenue"]] for row in store["daily_revenue"]]
        summary_copy = {key: value for key, value in store.items() if key != "daily_revenue"}
        store_summaries.append(summary_copy)

    return template.render(
        stores=store_results,
        store_summaries=store_summaries,
        chart_data=chart_data,
        api_url=api_url.rstrip("/"),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def build_dashboard(store_results, output_path, api_url=""):
    html = render_dashboard(store_results, api_url)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
