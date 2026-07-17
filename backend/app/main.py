import socket
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import migrate
from .deps import require_admin
from .routers import auth, catalog, options, orders, tables, users
from .ws import router as ws_router

# When the frontend has been built, this API server also serves it - one
# process for the whole shop; phones just open http://<pc-ip>:8000.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate.run()
    yield


app = FastAPI(title="OrderPad API", version="0.23.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/api/version")
def get_version():
    """Open (pre-auth) so the login screen can show what's running."""
    return {"version": app.version}


def _lan_ip() -> str:
    """Best-effort LAN address of this machine (no packet is sent)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


@app.get("/api/server-info")
def server_info(request: Request, _=Depends(require_admin)):
    """The address phones/tablets on the shop WiFi should open."""
    port = request.url.port or 8000
    if port == 5173:  # vite dev proxy: devices connect to the API port
        port = 8000
    ip = _lan_ip()
    return {"ip": ip, "port": port, "url": f"http://{ip}:{port}"}


for router in (auth.router, catalog.router, tables.router,
               orders.router, options.router, users.router):
    app.include_router(router, prefix="/api")
app.include_router(ws_router)


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"),
              name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Serve the built frontend; unknown paths fall back to index.html
        so client-side routes (/tables, /admin) survive a refresh."""
        if full_path.startswith(("api/", "ws/")):
            raise HTTPException(404, "Not found")
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
