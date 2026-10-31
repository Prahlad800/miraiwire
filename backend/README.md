# Miraiwire backend

Flask API with a health check at `GET /health`. It returns HTTP `200` and:

```json
{"status": "ok"}
```

## Windows setup

From this directory, create and activate a virtual environment, install Flask,
and start the development server:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Check `http://127.0.0.1:5000/health`. Run the test with:

```powershell
python -m unittest discover -s tests
```
