from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def build_dashboard(store_results, output_path):
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )
    template = environment.get_template("dashboard.html")

    chart_data = {}
    for store in store_results:
        chart_data[store["store"]] = [[row["date"], row["revenue"]] for row in store["daily_revenue"]]

    html = template.render(
        stores=store_results,
        chart_data=chart_data,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
