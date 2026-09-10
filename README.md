# MongoDB Generic Monitor

A generic, config-driven MongoDB query service — query any MongoDB database, export results as images (table or single-record card), and send them straight to a Matrix room. Includes a web UI, saved/scheduled automations, and support for multiple MongoDB profiles (local, VPN-gated, Atlas, etc.) — all managed through a single YAML config, no code changes needed.

## Features

- **Multi-database support** — connect to any number of MongoDB instances via named "profiles," switch between them from the UI or API.
- **Generic query engine** — `find`, `aggregate`, `insert`, `update`, `delete` on any collection, via REST API or the built-in web console.
- **Image export** — turn query results into a clean table image or a single highlighted "card" image (PNG).
- **Matrix integration** — send generated images directly to a Matrix room.
- **Saved automations** — save a query + image + Matrix target as a named automation, and schedule it to run on a fixed interval or a daily time. Runs in the background via APScheduler.
- **Web console (`index.html`)** — no-build, single-file frontend: build queries visually or write raw JSON, preview results, generate images, and manage automations and database profiles.
- **Fully generic** — adding a new database or changing Matrix settings is a config change, not a code change.

## Project structure

```
config.py           # loads config.yaml, manages profiles at runtime
config.yaml          # your local config (git-ignored — see Setup)
config.example.yaml  # template for config.yaml
database.py          # MongoDB connection management (per-profile, cached)
image_export.py       # renders query results as PNG (table / card)
matrix_client.py       # uploads images to Matrix and posts them to a room
main.py              # FastAPI app — all REST endpoints
scheduler.py          # background scheduler for automations (APScheduler)
saved_queries.py       # persistent storage for saved automations
saved_queries.yaml      # your saved automations data (git-ignored)
index.html            # web console (frontend)
requirements.txt       # Python dependencies
```

## Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/egmanya03/mongodb-generic-monitor.git
   cd mongodb-generic-monitor
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Create your config**
   ```bash
   cp config.example.yaml config.yaml
   ```
   Edit `config.yaml` and fill in:
   - `profiles.local.mongo_uri` / `db_name` — your MongoDB connection
   - `matrix.homeserver` — your Matrix homeserver URL
   - `matrix.access_token` — your Matrix bot/account access token (Element → Settings → Help & About → Advanced → Access Token)
   - `matrix.default_room_id` — the room to send images to by default

   `config.yaml` is git-ignored on purpose — never commit real credentials.

4. **Run the service**
   ```bash
   uvicorn main:app --reload
   ```
   API docs: `http://localhost:8000/docs`

5. **Open the web console**
   Open `index.html` in a browser (or serve it statically). Set "Service URL" to `http://localhost:8000` if it's not already.

## Adding another database

No code changes needed — either:
- Use the **Databases** tab in the web console ("+ Add database"), or
- Edit `config.yaml` directly and add a new block under `profiles:`.

## Security notes

- **CORS is wide open** (`allow_origins=["*"]`) in `main.py`, which is convenient for local/private-network use but **not safe for public internet deployment**. If you expose this service publicly, restrict `allow_origins` to your actual frontend origin(s).
- Never commit `config.yaml` or `saved_queries.yaml` — both are git-ignored by default since they can contain credentials or internal data.
- The `/…/delete` endpoint requires a non-empty filter when `many=true`, as a basic safety guard against accidental full-collection deletes — but there's no auth on any endpoint, so don't expose this service to an untrusted network without adding one.

## License

Add a license of your choice (MIT is a common default for a project like this).
