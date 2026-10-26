import re
from datetime import datetime

import pandas as pd
import yaml

EUR_TO_USD = 1.2

MISSING_MARKERS = {"", "NULL", "NAN", "NONE", "N/A"}

DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%y", "%d.%m.%Y", "%d-%b-%Y", "%d-%B-%Y"]
TIME_FORMATS = ["%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"]
FULL_FORMATS = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%a %b %d %H:%M:%S %Y"]


def build_timestamp_formats():
    formats = list(FULL_FORMATS)
    for date_format in DATE_FORMATS:
        for time_format in TIME_FORMATS:
            formats.append(f"{date_format} {time_format}")
            formats.append(f"{time_format} {date_format}")
    return formats


TIMESTAMP_FORMATS = build_timestamp_formats()


def clean_text_column(series):
    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.str.replace(r"\s+", " ", regex=True)
    is_missing = cleaned.str.upper().isin(MISSING_MARKERS)
    return cleaned.mask(is_missing)


def normalize_timestamp_text(text):
    text = text.upper()
    text = text.replace("A.M.", "AM").replace("P.M.", "PM")
    text = text.replace(";", " ").replace(",", " ")
    return " ".join(text.split())


def parse_timestamp(text):
    if pd.isna(text):
        return pd.NaT
    normalized = normalize_timestamp_text(str(text))
    for timestamp_format in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(normalized, timestamp_format)
        except ValueError:
            continue
    return pd.NaT


def parse_price_in_dollars(text):
    if pd.isna(text):
        return None
    text = str(text).strip().upper()

    if "€" in text or "EUR" in text:
        exchange_rate = EUR_TO_USD
    elif "$" in text or "USD" in text:
        exchange_rate = 1.0
    else:
        return None

    if "¢" in text:
        numbers = re.findall(r"\d+", text)
        if len(numbers) != 2:
            return None
        amount = int(numbers[0]) + int(numbers[1]) / 100
    else:
        match = re.search(r"\d+(\.\d*)?", text)
        if match is None:
            return None
        amount = float(match.group())

    return round(amount * exchange_rate, 2)


def load_orders(store_path):
    orders = pd.read_parquet(store_path / "orders.parquet")
    rows_loaded = len(orders)

    orders = orders.drop_duplicates()
    orders = orders.drop_duplicates(subset="id", keep="first")

    orders["timestamp"] = pd.to_datetime(orders["timestamp"].map(parse_timestamp))
    orders["unit_price"] = orders["unit_price"].map(parse_price_in_dollars).astype("float64")
    orders["quantity"] = pd.to_numeric(orders["quantity"], errors="coerce")
    orders["shipping"] = clean_text_column(orders["shipping"])

    is_valid = (
        orders["timestamp"].notna()
        & orders["unit_price"].notna()
        & orders["quantity"].notna()
        & (orders["quantity"] > 0)
        & (orders["unit_price"] > 0)
    )
    orders = orders[is_valid].copy()
    orders = orders.drop_duplicates(subset=["user_id", "book_id", "quantity", "unit_price", "timestamp"])

    orders["id"] = orders["id"].astype("int64")
    orders["user_id"] = orders["user_id"].astype("int64")
    orders["book_id"] = orders["book_id"].astype("int64")
    orders["quantity"] = orders["quantity"].astype("int64")

    orders["paid_price"] = (orders["quantity"] * orders["unit_price"]).round(2)

    orders["year"] = orders["timestamp"].dt.year
    orders["month"] = orders["timestamp"].dt.month
    orders["day"] = orders["timestamp"].dt.day
    orders["date"] = orders["timestamp"].dt.date

    print(f"  orders: loaded {rows_loaded}, kept {len(orders)}")
    return orders.reset_index(drop=True)


def load_users(store_path):
    users = pd.read_csv(store_path / "users.csv", dtype=str)
    rows_loaded = len(users)

    for column in ["name", "address", "phone", "email"]:
        users[column] = clean_text_column(users[column])

    users["email"] = users["email"].str.lower()
    users["phone"] = users["phone"].str.replace(r"\D", "", regex=True)
    users["phone"] = users["phone"].mask(users["phone"] == "")

    users["id"] = pd.to_numeric(users["id"], errors="coerce")
    users = users.dropna(subset=["id"])
    users["id"] = users["id"].astype("int64")

    users = users.drop_duplicates()
    users = users.drop_duplicates(subset="id", keep="first")

    print(f"  users: loaded {rows_loaded}, kept {len(users)}")
    return users.reset_index(drop=True)


def split_authors(author_text):
    if pd.isna(author_text):
        return ["Unknown author"]
    names = [name.strip() for name in str(author_text).split(",")]
    names = [name for name in names if name]
    return sorted(set(names))


def load_books(store_path):
    with open(store_path / "books.yaml", encoding="utf-8") as file:
        records = yaml.safe_load(file)
    books = pd.DataFrame(records)
    rows_loaded = len(books)

    books.columns = [str(column).lstrip(":") for column in books.columns]

    for column in ["title", "author", "genre", "publisher"]:
        books[column] = clean_text_column(books[column])

    books["id"] = pd.to_numeric(books["id"], errors="coerce")
    books = books.dropna(subset=["id"])
    books["id"] = books["id"].astype("int64")
    books["year"] = pd.to_numeric(books["year"], errors="coerce").astype("Int64")

    books = books.drop_duplicates(subset="id", keep="first")

    books["authors"] = books["author"].map(split_authors)
    books["author_set"] = books["authors"].map(", ".join)

    print(f"  books: loaded {rows_loaded}, kept {len(books)}")
    return books.reset_index(drop=True)
