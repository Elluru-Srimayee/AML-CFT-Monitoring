Development frontend README

Run frontend development server (dev):

1. From the `frontend/` folder, install dependencies:

```bash
npm install
```

2. Start the dev server (it will proxy API calls to the backend at http://localhost:8000):

```bash
npm start
```

3. In a separate terminal, run the backend API:

```bash
# create virtualenv and install requirements first, then
uvicorn src.api.server:app --reload
```

Build for production:

```bash
cd frontend
npm run build
# then start backend (it will serve the built files automatically if present)
uvicorn src.api.server:app --reload
```
