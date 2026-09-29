# AGENTS.md – ab-nach-hause

Context for AI agents working on this repo. Verbatim source: `course/prompts/background.md`.

## Roles & languages
- Course leader (the user) runs the course; the agent helps build course material, mainly **boilerplate code for coding exercises**.
- **Student-facing material: German.** Code, code comments/docstrings: English. Prompts, agent notes, agentic work: English.

## Course
- Official title: *„Ab nach Hause – Wie Google Maps & Co. den optimalen Weg finden“*.
- Topic: real-world application of maths – how navigation apps find routes. Map data (OpenStreetMap) → graph → **Dijkstra** and **A\***, in **Python**; result is a small web app.
- Audience: students from **grade 10** onwards (confirmed by the leader; "11th grade" in `background.md` is outdated). ~20 participants. Python experience helpful, not required.
- Format: **10 weekly online sessions, 90 min each, Tuesdays 17:00** (Microsoft Teams).
- Dates (3 Nov dropped, appended at end):
  | # | Date | # | Date |
  |---|------|---|------|
  | 1 | 06.10.2026 | 6 | 17.11.2026 |
  | 2 | 13.10.2026 | 7 | 24.11.2026 |
  | 3 | 20.10.2026 | 8 | 01.12.2026 |
  | 4 | 27.10.2026 | 9 | 08.12.2026 |
  | 5 | 10.11.2026 | 10 | 15.12.2026 |
- Content schedule (German, per lesson): see `README.MD` → „Zeitplan“.

## Mathe-AG At Home (framework)
- Free online program of *Bundesweite Mathematik-Wettbewerbe* (Bildung & Begabung) for students from grade 6, all of Germany; topics beyond the school curriculum.
- Courses: 8–10 units of 60–90 min over ≤ 3 months, weekly; usually led by (two) teacher-training students; ~20 participants.
- Students need no Teams account (access data provided). This course additionally needs: free GitHub account, laptop/desktop (no tablet), modern browser.
- Attendance certificate for regular, active participation; course leaders decide.
- Info: https://www.mathe-wettbewerbe.de/mathe-ah

## Repo layout & workflow
- Each student works in **their own fork, in a GitHub Codespace** (`.devcontainer/`: Python 3.11, requirements preinstalled, port 8080 forwarded, 16 GB RAM).
- `course/` – **internal, not for students directly** (presentations, exercises, course plan, agent background, prompts). Transparent: students can see it.
- `lektionen/lektionN/` – student material per session (German), e.g. `lektion1/QUICKSTART.MD`.
- `src/` – routing web app (FastAPI + Leaflet frontend in `static/`):
  - `config.py` reads `osm_data/city_config.json` (PBF file, viewport, default start/target).
  - `map_loader.py` loads OSM PBF via **pyrosm** → **igraph** graph (cycling network), cKDTree for snapping.
  - `route_service.py` – A\* implementation (reference; basis for exercises).
  - `server.py` – `/startup-coords`, `/stream-route` (SSE).
- `osm_data/` – sample data `Darmstadt.osm.pbf`; own extracts via https://extract.bbbike.org/.
- Run: `uvicorn --port 8080 src.server:app`.
- Tech preferences: PBF over .osm, igraph over networkx.
