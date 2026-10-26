from pathlib import Path

import duckdb

SQL_DIR = Path(__file__).resolve().parent / "sql"


def read_query(query_name):
    query_path = SQL_DIR / f"{query_name}.sql"
    return query_path.read_text(encoding="utf-8")


def run_query(connection, query_name):
    cursor = connection.execute(read_query(query_name))
    column_names = [column[0] for column in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(column_names, row)) for row in rows]


def analyze_store(orders, users, books):
    connection = duckdb.connect()
    connection.register("orders", orders[["id", "user_id", "book_id", "quantity", "unit_price", "paid_price", "date"]])
    connection.register("users", users[["id", "customer_id"]])
    connection.register("books", books[["id", "author_set"]])

    daily_revenue = run_query(connection, "daily_revenue")
    top_days = run_query(connection, "top_days")
    unique_users = run_query(connection, "unique_users")[0]["unique_users"]
    unique_author_sets = run_query(connection, "unique_author_sets")[0]["unique_author_sets"]
    most_popular_authors = run_query(connection, "most_popular_authors")
    best_customer = run_query(connection, "best_customer")[0]

    connection.close()

    for row in daily_revenue:
        row["date"] = row["date"].isoformat()

    for row in most_popular_authors:
        row["books_sold"] = int(row["books_sold"])

    return {
        "orders_count": len(orders),
        "total_revenue": round(float(orders["paid_price"].sum()), 2),
        "unique_users": int(unique_users),
        "unique_author_sets": int(unique_author_sets),
        "top_days": top_days,
        "most_popular_authors": most_popular_authors,
        "best_customer": {
            "user_ids": [int(user_id) for user_id in best_customer["user_ids"]],
            "total_spent": float(best_customer["total_spent"]),
        },
        "daily_revenue": daily_revenue,
    }
