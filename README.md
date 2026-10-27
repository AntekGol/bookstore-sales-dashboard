Bookstore sales analysis for the STORE folders, made with pandas and some SQL in DuckDB. The dashboard is generated into docs/index.html, and app.py runs the FastAPI backend for the AI chat and table explorer.

The data folder is not in the repo, to run it put the STORE folders into data/ and then:

pip install -r requirements.txt
python main.py
GEMINI_API_KEY=your_key uvicorn app:app --reload
