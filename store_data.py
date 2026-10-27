from dataclasses import dataclass

import pandas as pd

from analysis import analyze_store
from cleaning import load_books, load_orders, load_users
from customers import assign_customer_ids


@dataclass
class StoreData:
    name: str
    orders: pd.DataFrame
    users: pd.DataFrame
    books: pd.DataFrame
    summary: dict


def build_orders_table(orders, users, books):
    user_columns = users[["id", "customer_id", "name", "email"]].rename(
        columns={"id": "user_id", "name": "user_name"}
    )
    book_columns = books[["id", "title", "author_set", "genre"]].rename(
        columns={"id": "book_id", "author_set": "authors"}
    )

    table = orders.merge(user_columns, on="user_id", how="left")
    table = table.merge(book_columns, on="book_id", how="left")
    table = table.rename(columns={"id": "order_id"})

    table["date"] = pd.to_datetime(table["date"])
    table["weekday"] = table["date"].dt.day_name()

    columns = [
        "order_id", "date", "year", "month", "day", "weekday",
        "user_id", "customer_id", "user_name", "email",
        "book_id", "title", "authors", "genre",
        "quantity", "unit_price", "paid_price",
    ]
    return table[columns].sort_values("date").reset_index(drop=True)


def build_users_table(users, orders):
    spending = orders.groupby("user_id").agg(
        orders_count=("id", "count"),
        total_spent=("paid_price", "sum"),
    )
    linked_accounts = users.groupby("customer_id")["id"].count().rename("linked_accounts")

    table = users.merge(spending, left_on="id", right_index=True, how="left")
    table = table.merge(linked_accounts, left_on="customer_id", right_index=True, how="left")
    table["orders_count"] = table["orders_count"].fillna(0).astype("int64")
    table["total_spent"] = table["total_spent"].fillna(0).round(2)

    columns = [
        "id", "customer_id", "name", "email", "phone", "address",
        "linked_accounts", "orders_count", "total_spent",
    ]
    return table[columns].sort_values("id").reset_index(drop=True)


def build_books_table(books, orders):
    sales = orders.groupby("book_id").agg(
        books_sold=("quantity", "sum"),
        revenue=("paid_price", "sum"),
    )

    table = books.merge(sales, left_on="id", right_index=True, how="left")
    table["books_sold"] = table["books_sold"].fillna(0).astype("int64")
    table["revenue"] = table["revenue"].fillna(0).round(2)
    table["author_count"] = table["authors"].map(len)
    table["authors"] = table["author_set"]

    columns = [
        "id", "title", "authors", "author_count", "genre", "publisher", "year",
        "books_sold", "revenue",
    ]
    return table[columns].sort_values("id").reset_index(drop=True)


def load_store(store_path):
    print(store_path.name)
    orders = load_orders(store_path)
    users = assign_customer_ids(load_users(store_path))
    books = load_books(store_path)

    summary = {"store": store_path.name}
    summary.update(analyze_store(orders, users, books))

    return StoreData(
        name=store_path.name,
        orders=build_orders_table(orders, users, books),
        users=build_users_table(users, orders),
        books=build_books_table(books, orders),
        summary=summary,
    )


def load_all_stores(data_dir):
    store_paths = sorted(path for path in data_dir.iterdir() if path.is_dir())
    stores = {}
    for store_path in store_paths:
        stores[store_path.name] = load_store(store_path)
    return stores
