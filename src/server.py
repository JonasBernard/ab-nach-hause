import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from .config import BASE_DIR, default_start, default_target, pbf_viewport
from .map_loader import load_graph
from .route_service import compute_route


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_graph()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/startup-coords")
def get_startup_coords():
    return {
        "defaultView": [
            (pbf_viewport["left_lower"][0] + pbf_viewport["right_upper"][0]) / 2,
            (pbf_viewport["left_lower"][1] + pbf_viewport["right_upper"][1]) / 2,
        ],
        "startPos": default_start,
        "endPos": default_target,
    }


@app.get("/stream-route")
async def stream_route(start_lat: float, start_lon: float, target_lat: float, target_lon: float):
    """Compute a route and stream the result via SSE."""
    try:
        route = compute_route(start_lat, start_lon, target_lat, target_lon)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    async def event_generator():
        yield {
            "event": "start_snap",
            "data": json.dumps(route["start_coord"]),
        }
        yield {
            "event": "target_snap",
            "data": json.dumps(route["target_coord"]),
        }

        if route["status"] == "not_found":
            yield {
                "event": "error",
                "data": json.dumps({"message": "Keine Route gefunden"}),
            }
            return

        yield {
            "event": "route_found",
            "data": json.dumps({
                "distance_meters": route["distance_meters"],
                "coordinates": route["coordinates"],
            }),
        }

    return EventSourceResponse(event_generator())


app.mount("/", StaticFiles(directory=str(BASE_DIR / "static"), html=True), name="static")
