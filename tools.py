import pandas as pd

TABLE_NAMES = ["orders", "users", "books"]
VIEW_NAMES = ["overview", "explorer"]

FILTER_OPERATORS = [
    "equals", "not_equals", "contains", "not_contains",
    "starts_with", "not_starts_with", "ends_with", "not_ends_with",
    "greater_than", "greater_or_equal", "less_than", "less_or_equal",
    "matches_description", "not_matches_description",
]
TEXT_OPERATORS = [
    "contains", "not_contains", "starts_with", "not_starts_with", "ends_with", "not_ends_with",
]
COMPARISON_OPERATORS = ["greater_than", "greater_or_equal", "less_than", "less_or_equal"]

AGGREGATE_FUNCTIONS = ["count", "count_distinct", "sum", "avg", "min", "max"]
PANDAS_FUNCTIONS = {"sum": "sum", "avg": "mean", "min": "min", "max": "max"}

DEFAULT_ROW_LIMIT = 20
MAX_ROW_LIMIT = 50
MAX_DASHBOARD_ROWS = 5000


class ToolError(Exception):
    pass


def to_python_value(value):
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        return round(value, 2)
    return value


def frame_to_records(frame):
    records = []
    for row in frame.to_dict(orient="records"):
        records.append({column: to_python_value(value) for column, value in row.items()})
    return records


def read_filter_values(filter_spec):
    values = filter_spec.get("values")
    if values is None:
        values = filter_spec.get("value")
    if values is None:
        values = []
    if not isinstance(values, list):
        values = [values]

    values = [str(value).strip() for value in values if str(value).strip()]
    if not values:
        raise ToolError(f"Filter on column '{filter_spec.get('column')}' has no values.")
    return values


def convert_value(series, value):
    try:
        if pd.api.types.is_datetime64_any_dtype(series):
            return pd.to_datetime(value)
        if pd.api.types.is_numeric_dtype(series):
            return float(value)
    except (ValueError, TypeError):
        raise ToolError(f"Value '{value}' does not fit column '{series.name}'.")
    return value.lower()


def comparable_series(series):
    if pd.api.types.is_datetime64_any_dtype(series) or pd.api.types.is_numeric_dtype(series):
        return series
    return series.astype("string").str.lower()


def text_series(series):
    if pd.api.types.is_datetime64_any_dtype(series):
        series = series.dt.strftime("%Y-%m-%d")
    return series.astype("string").str.lower().fillna("")


def check_column(frame, column):
    if column not in frame.columns:
        available = ", ".join(frame.columns)
        raise ToolError(f"Unknown column '{column}'. Available columns: {available}.")


def keep_ties(sorted_values, limit):
    top = sorted_values.head(limit)
    if len(sorted_values) <= limit or limit == 0:
        return top
    last_value = top.iloc[-1]
    rest = sorted_values.iloc[limit:]
    tied = rest[rest == last_value]
    return pd.concat([top, tied])


class DataTools:
    def __init__(self, stores, semantic_matcher):
        self.stores = stores
        self.semantic_matcher = semantic_matcher
        self.handlers = {
            "get_store_summary": self.get_store_summary,
            "query_data": self.query_data,
            "get_customer_profile": self.get_customer_profile,
            "show_table": self.show_table,
            "open_view": self.open_view,
            "zoom_chart": self.zoom_chart,
            "reset_dashboard": self.reset_dashboard,
        }

    def run(self, tool_name, arguments):
        handler = self.handlers.get(tool_name)
        if handler is None:
            return {"error": f"Unknown tool '{tool_name}'."}, None
        try:
            return handler(**arguments)
        except ToolError as error:
            return {"error": str(error)}, None
        except TypeError as error:
            return {"error": f"Wrong arguments for {tool_name}: {error}"}, None

    def resolve_stores(self, store, allow_all=True):
        name = str(store or "").strip().upper().replace(" ", "")
        if name.isdigit():
            name = f"STORE{name}"
        if allow_all and name == "ALL":
            return list(self.stores.values())
        if name not in self.stores:
            choices = ", ".join(self.stores)
            raise ToolError(f"Unknown store '{store}'. Use one of: {choices}.")
        return [self.stores[name]]

    def get_table(self, store, table, allow_all=True):
        if table not in TABLE_NAMES:
            raise ToolError(f"Unknown table '{table}'. Use one of: {', '.join(TABLE_NAMES)}.")

        selected_stores = self.resolve_stores(store, allow_all)
        if len(selected_stores) == 1:
            return getattr(selected_stores[0], table)

        frames = []
        for store_data in selected_stores:
            frame = getattr(store_data, table).copy()
            frame.insert(0, "store", store_data.name)
            frames.append(frame)
        return pd.concat(frames, ignore_index=True)

    def table_rows(self, store, table):
        return frame_to_records(self.get_table(store, table, allow_all=False))

    def build_condition(self, frame, filter_spec):
        column = filter_spec.get("column")
        operator = filter_spec.get("operator")
        check_column(frame, column)
        if operator not in FILTER_OPERATORS:
            raise ToolError(f"Unknown operator '{operator}'. Use one of: {', '.join(FILTER_OPERATORS)}.")

        values = read_filter_values(filter_spec)
        series = frame[column]

        if operator in ["matches_description", "not_matches_description"]:
            distinct_values = series.dropna().astype(str).unique().tolist()
            matching_values = self.semantic_matcher.find_matching_values(distinct_values, values[0])
            condition = series.astype(str).isin(matching_values)
            if operator == "not_matches_description":
                return ~condition
            return condition

        if operator in TEXT_OPERATORS:
            text = text_series(series)
            condition = pd.Series(False, index=frame.index)
            for value in values:
                value = value.lower()
                if operator in ["contains", "not_contains"]:
                    matched = text.str.contains(value, regex=False)
                elif operator in ["starts_with", "not_starts_with"]:
                    matched = text.str.startswith(value)
                else:
                    matched = text.str.endswith(value)
                condition = condition | matched
            if operator in ["not_contains", "not_starts_with", "not_ends_with"]:
                condition = ~condition
            return condition.astype(bool)

        compared = comparable_series(series)

        if operator in ["equals", "not_equals"]:
            converted = [convert_value(series, value) for value in values]
            condition = compared.isin(converted).fillna(False).astype(bool)
            if operator == "not_equals":
                condition = ~condition
            return condition

        value = convert_value(series, values[0])
        if operator == "greater_than":
            condition = compared > value
        elif operator == "greater_or_equal":
            condition = compared >= value
        elif operator == "less_than":
            condition = compared < value
        else:
            condition = compared <= value
        return condition.fillna(False).astype(bool)

    def apply_filters(self, frame, filters, match="all"):
        if not filters:
            return frame

        conditions = [self.build_condition(frame, filter_spec) for filter_spec in filters]
        combined = conditions[0]
        for condition in conditions[1:]:
            if match == "any":
                combined = combined | condition
            else:
                combined = combined & condition
        return frame[combined]

    def aggregate(self, frame, function, column, group_by, sort_order, limit):
        if function not in AGGREGATE_FUNCTIONS:
            raise ToolError(f"Unknown aggregate '{function}'. Use one of: {', '.join(AGGREGATE_FUNCTIONS)}.")
        if function != "count":
            if not column:
                raise ToolError(f"Aggregate '{function}' needs a column.")
            check_column(frame, column)
        if function in ["sum", "avg"] and not pd.api.types.is_numeric_dtype(frame[column]):
            raise ToolError(f"Column '{column}' is not numeric, cannot use '{function}'.")

        if not group_by:
            if function == "count":
                value = len(frame)
            elif function == "count_distinct":
                value = frame[column].nunique()
            elif frame.empty:
                value = None
            else:
                value = frame[column].agg(PANDAS_FUNCTIONS[function])
            return {"value": to_python_value(value)}

        check_column(frame, group_by)
        grouped = frame.groupby(group_by)
        if function == "count":
            values = grouped.size()
        elif function == "count_distinct":
            values = grouped[column].nunique()
        else:
            values = grouped[column].agg(PANDAS_FUNCTIONS[function])

        values = values.sort_values(ascending=(sort_order == "asc"))
        top_values = keep_ties(values, limit)

        groups = []
        for key, value in top_values.items():
            groups.append({group_by: to_python_value(key), "value": to_python_value(value)})
        return {"groups_total": len(values), "groups": groups}

    def get_store_summary(self, store):
        summaries = []
        for store_data in self.resolve_stores(store):
            summary = {key: value for key, value in store_data.summary.items() if key != "daily_revenue"}
            summary["books_sold"] = int(store_data.orders["quantity"].sum())
            summary["first_order_date"] = to_python_value(store_data.orders["date"].min())
            summary["last_order_date"] = to_python_value(store_data.orders["date"].max())
            summaries.append(summary)
        return {"stores": summaries}, None

    def query_data(self, store, table, filters=None, match="all", aggregate=None, column=None,
                   group_by=None, sort_by=None, sort_order="desc", limit=DEFAULT_ROW_LIMIT):
        frame = self.get_table(store, table)
        filtered = self.apply_filters(frame, filters or [], match)
        limit = max(0, min(int(limit or DEFAULT_ROW_LIMIT), MAX_ROW_LIMIT))
        result = {"matching_rows": len(filtered)}

        if aggregate:
            result.update(self.aggregate(filtered, aggregate, column, group_by, sort_order, limit))
            return result, None

        if sort_by:
            check_column(filtered, sort_by)
            filtered = filtered.sort_values(sort_by, ascending=(sort_order == "asc"))
        result["rows"] = frame_to_records(filtered.head(limit))
        result["rows_shown"] = len(result["rows"])
        return result, None

    def describe_customer(self, store_data, customer_id):
        accounts = store_data.users[store_data.users["customer_id"] == customer_id]
        orders = store_data.orders[store_data.orders["customer_id"] == customer_id]

        spending = store_data.orders.groupby("customer_id")["paid_price"].sum()
        spending = spending.sort_values(ascending=False)
        spending_rank = None
        if customer_id in spending.index:
            spending_rank = spending.index.get_loc(customer_id) + 1

        top_books = orders.groupby("title")["quantity"].sum().sort_values(ascending=False).head(5)

        return {
            "customer_id": int(customer_id),
            "user_ids": sorted(int(user_id) for user_id in accounts["id"]),
            "accounts": frame_to_records(accounts[["id", "name", "email", "phone", "address"]]),
            "orders_count": len(orders),
            "books_bought": int(orders["quantity"].sum()),
            "total_spent": round(float(orders["paid_price"].sum()), 2),
            "spending_rank": spending_rank,
            "customers_in_store": int(store_data.users["customer_id"].nunique()),
            "first_order": to_python_value(orders["date"].min()) if len(orders) else None,
            "last_order": to_python_value(orders["date"].max()) if len(orders) else None,
            "top_books": [{"title": title, "quantity": int(quantity)} for title, quantity in top_books.items()],
        }

    def get_customer_profile(self, store, user_id=None, search=None):
        store_data = self.resolve_stores(store, allow_all=False)[0]
        users = store_data.users

        if user_id is not None:
            try:
                matches = users[users["id"] == int(user_id)]
            except ValueError:
                raise ToolError(f"User id '{user_id}' is not a number.")
        elif search:
            text = str(search).lower()
            digits = "".join(character for character in text if character.isdigit())
            condition = (
                users["name"].str.lower().str.contains(text, regex=False, na=False)
                | users["email"].str.lower().str.contains(text, regex=False, na=False)
                | users["address"].str.lower().str.contains(text, regex=False, na=False)
            )
            if len(digits) >= 4:
                condition = condition | users["phone"].str.contains(digits, regex=False, na=False)
            matches = users[condition]
        else:
            raise ToolError("Give user_id or search.")

        if matches.empty:
            return {"error": "No user matches this id or search text."}, None

        customer_ids = matches["customer_id"].unique().tolist()
        if len(customer_ids) > 5:
            candidates = frame_to_records(matches[["id", "customer_id", "name", "email"]].head(10))
            return {"message": "Too many customers match, ask the user to be more specific.",
                    "matching_customers": len(customer_ids), "candidates": candidates}, None

        profiles = [self.describe_customer(store_data, customer_id) for customer_id in customer_ids]
        return {"customers": profiles}, None

    def show_table(self, store, table, filters=None, match="all", sort_by=None, sort_order="desc", title=""):
        store_data = self.resolve_stores(store, allow_all=False)[0]
        frame = self.get_table(store_data.name, table, allow_all=False)
        filtered = self.apply_filters(frame, filters or [], match)

        if sort_by:
            check_column(filtered, sort_by)
            filtered = filtered.sort_values(sort_by, ascending=(sort_order == "asc"))

        action = {
            "type": "show_table",
            "store": store_data.name,
            "table": table,
            "title": title or "Filtered by AI",
            "total_rows": len(filtered),
            "rows": frame_to_records(filtered.head(MAX_DASHBOARD_ROWS)),
        }
        result = {
            "matching_rows": len(filtered),
            "first_rows": frame_to_records(filtered.head(5)),
            "message": "The table is now visible in the Data explorer view of the dashboard.",
        }
        return result, action

    def open_view(self, store, view, table=None):
        store_data = self.resolve_stores(store, allow_all=False)[0]
        if view not in VIEW_NAMES:
            raise ToolError(f"Unknown view '{view}'. Use one of: {', '.join(VIEW_NAMES)}.")
        if table is not None and table not in TABLE_NAMES:
            raise ToolError(f"Unknown table '{table}'. Use one of: {', '.join(TABLE_NAMES)}.")

        action = {"type": "open_view", "store": store_data.name, "view": view, "table": table}
        return {"message": f"Opened {view} of {store_data.name}."}, action

    def zoom_chart(self, store, date_from, date_to):
        store_data = self.resolve_stores(store, allow_all=False)[0]
        try:
            start = pd.to_datetime(date_from)
            end = pd.to_datetime(date_to)
        except (ValueError, TypeError):
            raise ToolError("Dates must be in YYYY-MM-DD format.")
        if start > end:
            start, end = end, start

        action = {
            "type": "zoom_chart",
            "store": store_data.name,
            "date_from": start.strftime("%Y-%m-%d"),
            "date_to": end.strftime("%Y-%m-%d"),
        }
        return {"message": f"Chart of {store_data.name} zoomed to {action['date_from']} - {action['date_to']}."}, action

    def reset_dashboard(self):
        return {"message": "Dashboard filters and chart zoom were reset."}, {"type": "reset"}
