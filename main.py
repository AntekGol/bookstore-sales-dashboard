import json
import os
from pathlib import Path

from dotenv import load_dotenv

from charts import save_daily_revenue_chart
from dashboard import build_dashboard
from store_data import load_store
from tools import frame_to_records

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "output"
DOCS_DIR = PROJECT_DIR / "docs"
ASSETS_DIR = DOCS_DIR / "assets"
DASHBOARD_PATH = DOCS_DIR / "index.html"


def print_summary(results):
    print("  top 5 days by revenue:")
    for row in results["top_days"]:
        print(f"    {row['day']}  ${row['revenue']:,.2f}")
    print(f"  unique users: {results['unique_users']}")
    print(f"  unique sets of authors: {results['unique_author_sets']}")
    for row in results["most_popular_authors"]:
        print(f"  most popular author(s): {row['author_set']} ({row['books_sold']} books sold)")
    best_customer = results["best_customer"]
    print(f"  best buyer: {best_customer['user_ids']} (${best_customer['total_spent']:,.2f})")
    print()


def save_store_asset(store):
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    order_columns = ["order_id", "date", "user_id", "book_id", "quantity", "unit_price", "paid_price"]
    orders_rows = [
        [
            row["order_id"],
            row["date"],
            row["user_id"],
            row["book_id"],
            row["quantity"],
            row["unit_price"],
            row["paid_price"],
        ]
        for row in frame_to_records(store.orders[order_columns])
    ]
    payload = {
        "books": frame_to_records(store.books),
        "users": frame_to_records(store.users),
        "orders": orders_rows,
    }
    asset_path = ASSETS_DIR / f"{store.name}.json"
    asset_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def process_store(store_path):
    store = load_store(store_path)

    chart_path = OUTPUT_DIR / store.name / "daily_revenue.png"
    save_daily_revenue_chart(store.summary["daily_revenue"], store.name, chart_path)
    save_store_asset(store)

    print_summary(store.summary)
    return store.summary


def main():
    load_dotenv(PROJECT_DIR / ".env")
    store_paths = sorted(path for path in DATA_DIR.iterdir() if path.is_dir())

    all_results = []
    for store_path in store_paths:
        all_results.append(process_store(store_path))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "results.json", "w", encoding="utf-8") as file:
        json.dump(all_results, file, indent=2)

    api_url = os.getenv("DASHBOARD_API_URL", "")
    build_dashboard(all_results, DASHBOARD_PATH, api_url)
    print(f"dashboard saved to {DASHBOARD_PATH}")


if __name__ == "__main__":
    main()
