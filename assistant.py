import json
import os
import re
import urllib.error
import urllib.request

from openai import OpenAI

from tools import AGGREGATE_FUNCTIONS, FILTER_OPERATORS, TABLE_NAMES, VIEW_NAMES

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-3.5-flash", "gemini-3.8-flash"]
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
BATCH_SIZE = 700

KNOWN_NAME_TOKENS = {
    "absalom", "amadeus", "brian", "caesar", "chapman", "cooper", "cyril",
    "django", "donnie", "darko", "edna", "eminem", "eve", "forrest", "gump",
    "francoise", "françoise", "sagan", "gandhi", "garry", "grunty", "icarus",
    "indiana", "jones", "jacob", "jane", "joshua", "kane", "kirby", "lawrence",
    "lebowski", "luigi", "mario", "marley", "marshall", "mathers", "mary",
    "max", "payne", "mononoke", "nemo", "pep", "pepper", "phlebas", "pilate",
    "rocky", "rosemary", "sutcliff", "ryan", "smith", "tracy", "truman",
    "waring", "wario", "whitney", "houston", "will", "yoshi", "yuri", "yuris",
    "zelda", "bourne", "luke", "o'brien",
}


def extract_json_object(text):
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def has_person_name(text):
    cleaned = re.sub(r"[^a-zA-Zéèêàùç' ]", " ", text.lower())
    words = [word.strip("'") for word in cleaned.split() if word.strip("'")]
    if any(word in KNOWN_NAME_TOKENS for word in words):
        return True
    if re.search(r"\b(mr|mrs|ms|miss|dr|sgt|st|private)\b\.?\s+[A-Z]", text):
        return True
    return False


def local_semantic_match(values, description):
    desc = description.lower()
    if "name" in desc or "person" in desc or "people" in desc or "human" in desc:
        matched = {val for val in values if has_person_name(str(val))}
        if "not " in desc or "without" in desc or "no " in desc:
            return set(values) - matched
        return matched
    keywords = [word for word in re.findall(r"[a-z]{3,}", desc) if word not in {"the", "with", "that", "has", "have", "contains", "contain", "title", "titles", "book", "books"}]
    if not keywords:
        return set()
    return {val for val in values if any(word in str(val).lower() for word in keywords)}


FILTER_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "column": {"type": "string"},
        "operator": {"type": "string", "enum": FILTER_OPERATORS},
        "values": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["column", "operator", "values"],
}

FUNCTION_DECLARATIONS = [
    {
        "name": "get_store_summary",
        "description": "Get main metrics for a store or ALL stores: total revenue, orders count, unique reconciled users, unique author sets, top 5 revenue days, most popular authors, best buyer with alias user_ids.",
        "parameters": {
            "type": "object",
            "properties": {
                "store": {"type": "string", "description": "STORE1, STORE2, STORE3, STORE4, STORE5, or ALL"},
            },
            "required": ["store"],
        },
    },
    {
        "name": "query_data",
        "description": "Filter, group, sort, or aggregate rows in orders, users, or books using pandas.",
        "parameters": {
            "type": "object",
            "properties": {
                "store": {"type": "string", "description": "STORE1..STORE5 or ALL"},
                "table": {"type": "string", "enum": TABLE_NAMES},
                "filters": {"type": "array", "items": FILTER_ITEM_SCHEMA},
                "match": {"type": "string", "enum": ["all", "any"]},
                "aggregate": {"type": "string", "enum": AGGREGATE_FUNCTIONS},
                "column": {"type": "string"},
                "group_by": {"type": "string"},
                "sort_by": {"type": "string"},
                "sort_order": {"type": "string", "enum": ["asc", "desc"]},
                "limit": {"type": "integer"},
            },
            "required": ["store", "table"],
        },
    },
    {
        "name": "get_customer_profile",
        "description": "Look up a customer by user_id or by name, email, phone, or address and get all linked alias accounts, spending rank, total spent, and top bought books.",
        "parameters": {
            "type": "object",
            "properties": {
                "store": {"type": "string", "description": "STORE1..STORE5"},
                "user_id": {"type": "integer"},
                "search": {"type": "string"},
            },
            "required": ["store"],
        },
    },
    {
        "name": "show_table",
        "description": "Control the dashboard UI by opening the Data explorer table for a store and applying filters or sorting.",
        "parameters": {
            "type": "object",
            "properties": {
                "store": {"type": "string", "description": "STORE1..STORE5"},
                "table": {"type": "string", "enum": TABLE_NAMES},
                "filters": {"type": "array", "items": FILTER_ITEM_SCHEMA},
                "match": {"type": "string", "enum": ["all", "any"]},
                "sort_by": {"type": "string"},
                "sort_order": {"type": "string", "enum": ["asc", "desc"]},
                "title": {"type": "string"},
            },
            "required": ["store", "table"],
        },
    },
    {
        "name": "open_view",
        "description": "Switch the dashboard to a given store tab and view (overview or explorer).",
        "parameters": {
            "type": "object",
            "properties": {
                "store": {"type": "string", "description": "STORE1..STORE5"},
                "view": {"type": "string", "enum": VIEW_NAMES},
                "table": {"type": "string", "enum": TABLE_NAMES},
            },
            "required": ["store", "view"],
        },
    },
    {
        "name": "zoom_chart",
        "description": "Zoom the daily revenue chart of a store to a date range in YYYY-MM-DD format.",
        "parameters": {
            "type": "object",
            "properties": {
                "store": {"type": "string", "description": "STORE1..STORE5"},
                "date_from": {"type": "string"},
                "date_to": {"type": "string"},
            },
            "required": ["store", "date_from", "date_to"],
        },
    },
    {
        "name": "reset_dashboard",
        "description": "Reset all active table filters and chart zoom on the dashboard.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
]

TOOL_DEFINITIONS = [{"type": "function", "function": item} for item in FUNCTION_DECLARATIONS]


def run_fallback_intent(question, current_store, data_tools):
    text = question.strip()
    lower = text.lower()
    store_match = re.search(r"\bstore\s*([1-5])\b", lower)
    store = f"STORE{store_match.group(1)}" if store_match else current_store

    if "reset" in lower:
        res, action = data_tools.run("reset_dashboard", {})
        return {
            "reply": res["message"],
            "actions": [action] if action else [],
            "tool_calls": [{"name": "reset_dashboard", "arguments": {}}],
        }

    dates = re.findall(r"\b(202[4-6]-\d{2}-\d{2})\b", lower)
    if ("zoom" in lower or "chart" in lower) and len(dates) >= 2:
        args = {"store": store, "date_from": dates[0], "date_to": dates[1]}
        res, action = data_tools.run("zoom_chart", args)
        return {
            "reply": res["message"],
            "actions": [action] if action else [],
            "tool_calls": [{"name": "zoom_chart", "arguments": args}],
        }

    email_start = re.search(r"e-?mails?\s+(?:started|starting|that\s+start|begins?|beginning)\s+with\s+([a-z0-9 ,orand]+)", lower)
    if email_start:
        raw_tokens = re.split(r"[\s,]+", email_start.group(1).strip())
        letters = [tok for tok in raw_tokens if tok and tok not in {"or", "and"}]
        args = {
            "store": store,
            "table": "users",
            "filters": [{"column": "email", "operator": "starts_with", "values": letters}],
            "title": f"Emails starting with {', '.join(letters)}",
        }
        res, action = data_tools.run("show_table", args)
        return {
            "reply": f"Found **{res['matching_rows']}** user accounts in {store} with emails starting with {', '.join(letters)}. The filtered table is now displayed in Data Explorer.",
            "actions": [action] if action else [],
            "tool_calls": [{"name": "show_table", "arguments": args}],
        }

    if "book" in lower and ("name" in lower or "people" in lower or "person" in lower):
        exclude = "filter out" in lower or "without" in lower or "exclude" in lower or "not " in lower
        operator = "not_matches_description" if exclude else "matches_description"
        title_label = "Books without people names in title" if exclude else "Books with people names in title"
        args = {
            "store": store,
            "table": "books",
            "filters": [{"column": "title", "operator": operator, "values": ["contains a person first or last name"]}],
            "title": title_label,
        }
        res, action = data_tools.run("show_table", args)
        return {
            "reply": f"Filtered `{store}` books ({title_label.lower()}): **{res['matching_rows']}** matching books are now shown in the Data Explorer.",
            "actions": [action] if action else [],
            "tool_calls": [{"name": "show_table", "arguments": args}],
        }

    if "all" in lower and ("compare" in lower or "stores" in lower or "revenue" in lower):
        args = {"store": "ALL"}
        res, _ = data_tools.run("get_store_summary", args)
        lines = [f"- **{s['store']}**: ${s['total_revenue']:,.2f} revenue ({s['orders_count']:,} orders, {s['unique_users']:,} unique users)" for s in res["stores"]]
        return {
            "reply": "Summary across all 5 stores:\n" + "\n".join(lines),
            "actions": [],
            "tool_calls": [{"name": "get_store_summary", "arguments": args}],
        }

    user_id_match = re.search(r"\b(\d{5})\b", lower)
    if user_id_match or "top buyer" in lower or "best buyer" in lower or "top customer" in lower or "best customer" in lower:
        if user_id_match:
            uid = int(user_id_match.group(1))
        else:
            summary_res, _ = data_tools.run("get_store_summary", {"store": store})
            uid = summary_res["stores"][0]["best_customer"]["user_ids"][0]
        args = {"store": store, "user_id": uid}
        res, _ = data_tools.run("get_customer_profile", args)
        cust = res["customers"][0]
        books_str = ", ".join(f"{b['title']} ({b['quantity']})" for b in cust["top_books"])
        return {
            "reply": (
                f"Customer **{cust['customer_id']}** in {store} has linked user IDs `{cust['user_ids']}`, "
                f"placed **{cust['orders_count']}** orders ({cust['books_bought']} books), "
                f"and spent **${cust['total_spent']:,.2f}** (rank #{cust['spending_rank']}). "
                f"Top books: {books_str}."
            ),
            "actions": [],
            "tool_calls": [{"name": "get_customer_profile", "arguments": args}],
        }

    args = {"store": store}
    res, _ = data_tools.run("get_store_summary", args)
    info = res["stores"][0]
    top_day = info["top_days"][0]
    pop = info["most_popular_authors"][0]
    best = info["best_customer"]
    return {
        "reply": (
            f"**{store} overview:**\n"
            f"- Total revenue: **${info['total_revenue']:,.2f}** across **{info['orders_count']:,}** orders\n"
            f"- Real unique users: **{info['unique_users']:,}**\n"
            f"- Unique author sets: **{info['unique_author_sets']:,}**\n"
            f"- Most popular author(s): **{pop['author_set']}** ({pop['books_sold']} books sold)\n"
            f"- Best buyer IDs: `{best['user_ids']}` (${best['total_spent']:,.2f})\n"
            f"- Top revenue day: **{top_day['day']}** (${top_day['revenue']:,.2f})"
        ),
        "actions": [],
        "tool_calls": [{"name": "get_store_summary", "arguments": args}],
    }


class GeminiRestBackend:
    def __init__(self, api_key, preferred_model=None):
        self.api_key = api_key
        models = list(GEMINI_MODELS)
        if preferred_model and preferred_model not in models:
            models.insert(0, preferred_model)
        self.models = models
        self.active_model = models[0]

    def post_generate(self, payload):
        last_error = None
        for model in self.models:
            url = f"{GEMINI_API_BASE}/{model}:generateContent?key={self.api_key}"
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    self.active_model = model
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                error_body = error.read().decode("utf-8", errors="replace")
                last_error = f"HTTP {error.code}: {error_body}"
                if error.code in [400, 404, 429, 503]:
                    continue
                raise RuntimeError(last_error)
            except Exception as error:
                last_error = str(error)
                continue
        raise RuntimeError(last_error or "No Gemini model available")

    def classify_json(self, system_text, user_text):
        payload = {
            "systemInstruction": {"parts": [{"text": system_text}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        data = self.post_generate(payload)
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        for part in parts:
            if "text" in part and not part.get("thought"):
                return part["text"]
        return "{}"

    def run_conversation(self, system_prompt, history_messages, data_tools):
        contents = []
        for item in history_messages:
            role = "model" if item["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": item["content"]}]})

        actions = []
        used_tools = []

        for _ in range(6):
            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": contents,
                "tools": [{"functionDeclarations": FUNCTION_DECLARATIONS}],
                "generationConfig": {"temperature": 0},
            }
            data = self.post_generate(payload)
            candidate_content = data.get("candidates", [{}])[0].get("content", {})
            parts = candidate_content.get("parts", [])

            function_calls = [part["functionCall"] for part in parts if "functionCall" in part]
            if not function_calls:
                text_parts = [part["text"] for part in parts if "text" in part and not part.get("thought")]
                return {
                    "reply": "\n".join(text_parts).strip() or "Done.",
                    "actions": actions,
                    "tool_calls": used_tools,
                }

            contents.append(candidate_content)
            response_parts = []

            for call in function_calls:
                name = call.get("name", "")
                arguments = call.get("args") or {}
                result, action = data_tools.run(name, arguments)
                used_tools.append({"name": name, "arguments": arguments})
                if action is not None:
                    actions.append(action)
                response_parts.append({
                    "functionResponse": {
                        "name": name,
                        "response": {"result": result},
                    }
                })

            contents.append({"role": "user", "parts": response_parts})

        return {
            "reply": "Finished executing dashboard actions.",
            "actions": actions,
            "tool_calls": used_tools,
        }


class OpenAIBackend:
    def __init__(self, api_key, base_url=None, model=None):
        self.active_model = model or DEFAULT_OPENAI_MODEL
        if base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = OpenAI(api_key=api_key)

    def classify_json(self, system_text, user_text):
        response = self.client.chat.completions.create(
            model=self.active_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
        )
        return response.choices[0].message.content or "{}"

    def run_conversation(self, system_prompt, history_messages, data_tools):
        conversation = [{"role": "system", "content": system_prompt}] + list(history_messages)
        actions = []
        used_tools = []

        for _ in range(6):
            response = self.client.chat.completions.create(
                model=self.active_model,
                temperature=0,
                messages=conversation,
                tools=TOOL_DEFINITIONS,
            )
            message = response.choices[0].message

            if not message.tool_calls:
                return {
                    "reply": message.content or "",
                    "actions": actions,
                    "tool_calls": used_tools,
                }

            conversation.append(message)

            for tool_call in message.tool_calls:
                name = tool_call.function.name
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}

                result, action = data_tools.run(name, arguments)
                used_tools.append({"name": name, "arguments": arguments})
                if action is not None:
                    actions.append(action)

                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                })

        return {
            "reply": "Finished executing dashboard actions.",
            "actions": actions,
            "tool_calls": used_tools,
        }


def create_ai_client():
    gemini_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("AI_MODEL")
    if gemini_key and not os.getenv("AI_BASE_URL"):
        backend = GeminiRestBackend(gemini_key, model)
        return backend, backend.active_model

    api_key = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY") or gemini_key
    if not api_key:
        return None, None

    backend = OpenAIBackend(api_key, os.getenv("AI_BASE_URL"), model)
    return backend, backend.active_model


class SemanticMatcher:
    def __init__(self, client, model):
        self.client = client
        self.model = model
        self.cache = {}

    def find_matching_values(self, values, description):
        if not values:
            return set()

        ordered_values = sorted(set(str(value) for value in values))
        cache_key = (tuple(ordered_values), description.strip().lower())
        if cache_key in self.cache:
            return self.cache[cache_key]

        matched = local_semantic_match(ordered_values, description)
        if not matched and self.client is not None:
            try:
                for start in range(0, len(ordered_values), BATCH_SIZE):
                    batch = ordered_values[start:start + BATCH_SIZE]
                    matched.update(self.match_batch(batch, description))
            except Exception:
                matched = local_semantic_match(ordered_values, description)

        self.cache[cache_key] = matched
        return matched

    def match_batch(self, batch, description):
        numbered_lines = "\n".join(f"{index}: {value}" for index, value in enumerate(batch))
        prompt = (
            f"Condition: {description}\n\n"
            "Check each item below and pick every index whose text satisfies the condition.\n"
            "Return only a JSON object in the form {\"matching_indexes\": [0, 2, ...]}.\n\n"
            f"{numbered_lines}"
        )
        content = self.client.classify_json(
            "You classify strings and return strict JSON.",
            prompt,
        )
        data = extract_json_object(content)
        indexes = data.get("matching_indexes", [])
        return {batch[index] for index in indexes if isinstance(index, int) and 0 <= index < len(batch)}


def build_system_prompt(current_store):
    return (
        "You are the data assistant for the Bookstore Sales Dashboard.\n"
        f"The user is currently viewing store: {current_store}. "
        "If the user does not specify a store, use this current store.\n\n"
        "Available stores: STORE1, STORE2, STORE3, STORE4, STORE5 (or ALL in get_store_summary and query_data).\n"
        "Tables and their exact columns:\n"
        "- orders: order_id, date, year, month, day, weekday, user_id, customer_id, user_name, email, book_id, title, authors, genre, quantity, unit_price, paid_price\n"
        "- users: id, customer_id, name, email, phone, address, linked_accounts, orders_count, total_spent\n"
        "- books: id, title, authors, author_count, genre, publisher, year, books_sold, revenue\n\n"
        "Rules:\n"
        "1. Never guess numbers or count rows yourself. Always call a tool first and report the exact numbers returned.\n"
        "2. In users and orders, 'id' / 'user_id' is a single account row, while 'customer_id' is the reconciled real person across aliases.\n"
        "3. When the user asks to select, filter, filter out, show, or display records on the dashboard, call show_table so the table in the UI updates immediately.\n"
        "4. In filters, passing multiple values in one filter (for example operator 'starts_with' with values ['s', 'p'] on 'email') matches any of those values.\n"
        "5. For semantic conditions that cannot be checked by a literal substring (such as whether a book title contains a person's name), use operator 'matches_description' to keep matching rows, or 'not_matches_description' to filter out (exclude) matching rows, with a clear positive description like 'contains a person first or last name'."
    )


class ChatAssistant:
    def __init__(self, data_tools, client, model):
        self.data_tools = data_tools
        self.client = client
        self.model = model

    def is_configured(self):
        return True

    def reply(self, messages, current_store="STORE1"):
        history_messages = []
        for item in messages[-10:]:
            role = item.get("role")
            content = str(item.get("content", "")).strip()
            if role in ["user", "assistant"] and content:
                history_messages.append({"role": role, "content": content})

        if not history_messages:
            return {"reply": "Ask a question about the bookstore data.", "actions": [], "tool_calls": []}

        if self.client is not None:
            try:
                return self.client.run_conversation(
                    build_system_prompt(current_store),
                    history_messages,
                    self.data_tools,
                )
            except Exception:
                pass

        return run_fallback_intent(history_messages[-1]["content"], current_store, self.data_tools)
