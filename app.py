from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from assistant import ChatAssistant, SemanticMatcher, create_ai_client
from dashboard import render_dashboard
from store_data import load_all_stores
from tools import DataTools, ToolError

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"

load_dotenv(PROJECT_DIR / ".env")

stores = load_all_stores(DATA_DIR)
store_summaries = [store.summary for store in stores.values()]

ai_client, ai_model = create_ai_client()
semantic_matcher = SemanticMatcher(ai_client, ai_model)
data_tools = DataTools(stores, semantic_matcher)
chat_assistant = ChatAssistant(data_tools, ai_client, ai_model)

app = FastAPI(title="Bookstore Sales Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    messages: list[dict]
    current_store: str = "STORE1"


@app.get("/", response_class=HTMLResponse)
def index():
    return render_dashboard(store_summaries, api_url="")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "stores": list(stores.keys()),
        "ai_configured": chat_assistant.is_configured(),
        "model": ai_model,
    }


@app.get("/api/table/{store}/{table}")
def get_table(store: str, table: str):
    try:
        rows = data_tools.table_rows(store, table)
    except ToolError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {
        "store": store.upper(),
        "table": table,
        "total_rows": len(rows),
        "rows": rows,
    }


@app.post("/api/chat")
def chat(request: ChatRequest):
    return chat_assistant.reply(request.messages, request.current_store)
