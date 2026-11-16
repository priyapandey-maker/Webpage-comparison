# Historical Webpage Comparison

This project connects the existing Python comparison engine to the existing React result dashboard through a small local FastAPI bridge.

## 1. Start the backend

```bash
cd comparison-engine
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://127.0.0.1:8000/api/compare`.

## 2. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173/`.

## Data flow

The frontend sends `version1` and `version2` as multipart HTML files. The API runs Member 2's existing comparison functions in a temporary directory, deletes the temporary files after the request, and returns ResultsPage-ready JSON through `result_adapter.py`.
