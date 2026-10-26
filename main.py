import json
from pathlib import Path

from analysis import analyze_store
from charts import save_daily_revenue_chart
from cleaning import load_books, load_orders, load_users
from customers import assign_customer_ids
from dashboard import build_dashboard

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "output"
DASHBOARD_PATH = PROJECT_DIR / "docs" / "index.html"


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


def process_store(store_path):
    print(store_path.name)

    orders = load_orders(store_path)
    users = assign_customer_ids(load_users(store_path))
    books = load_books(store_path)

    results = {"store": store_path.name}
    results.update(analyze_store(orders, users, books))

    chart_path = OUTPUT_DIR / store_path.name / "daily_revenue.png"
    save_daily_revenue_chart(results["daily_revenue"], store_path.name, chart_path)

    print_summary(results)
    return results


def main():
    store_paths = sorted(path for path in DATA_DIR.iterdir() if path.is_dir())

    all_results = []
    for store_path in store_paths:
        all_results.append(process_store(store_path))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "results.json", "w", encoding="utf-8") as file:
        json.dump(all_results, file, indent=2)

    build_dashboard(all_results, DASHBOARD_PATH)
    print(f"dashboard saved to {DASHBOARD_PATH}")


if __name__ == "__main__":
    main()
