# Historical Webpage Comparison — Result Presentation Module

Standalone React + Vite frontend for selecting two HTML webpage versions and presenting structured, verified changes. HTML processing remains entirely in the local Python comparison service.

The upload screen keeps the two selected `File` objects in React state. `src/services/comparisonService.js` sends them to the local FastAPI endpoint at `http://127.0.0.1:8000/api/compare`.

## Run locally

```bash
npm install
npm run dev
```

Then open the local URL printed by Vite (normally `http://localhost:5173`).

## Production build

```bash
npm run build
npm run preview
```

The API base URL can be changed with `VITE_API_BASE_URL`.
