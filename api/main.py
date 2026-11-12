"""
FastAPI application for The Iron Throne RPG Telegram Mini App.
"""
import time
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, Any

from pathlib import Path
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import API_HOST, API_PORT
from database import init_db
from api.rate_limiter import rate_limit_dependency
from api.routers.player import router as player_router
from api.routers.actions import router as actions_router
from api.routers.errors import router as errors_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # 1. Startup: Verify database connection and schema
    await init_db()
    yield
    # 2. Shutdown: Cleanup connections if needed


app = FastAPI(
    title="The Iron Throne — Mini App API",
    description="Backend API for The Iron Throne: Xonadonlar Urushi Telegram Mini App",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)

# CORS sozlamalari (Telegram WebApp va mahalliy testlar uchun)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_and_security_middleware(request: Request, call_next):
    """
    So'rovlar vaqti va xavfsizlik sarlavhalarini qayta ishlash.
    """
    start_time = time.time()
    try:
        response = await call_next(request)
    except (StarletteHTTPException, HTTPException) as http_exc:
        process_time = (time.time() - start_time) * 1000
        return JSONResponse(
            status_code=http_exc.status_code,
            content={
                "success": False,
                "error": http_exc.detail,
                "status_code": http_exc.status_code,
                "duration_ms": round(process_time, 2),
            },
            headers=getattr(http_exc, "headers", None)
        )
    except RequestValidationError as val_exc:
        process_time = (time.time() - start_time) * 1000
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": "Ma'lumotlar validatsiyasida xatolik.",
                "detail": val_exc.errors(),
                "status_code": 422,
                "duration_ms": round(process_time, 2),
            }
        )
    except Exception as exc:
        import traceback
        tb_str = traceback.format_exc()
        process_time = (time.time() - start_time) * 1000

        # Tizim xatolarini avtomatik ERROR_CHAT_ID guruhiga yuborish
        try:
            from core.error_reporter import report_system_error
            await report_system_error(
                source="api",
                error_type=type(exc).__name__,
                error_message=str(exc),
                handler_name=f"{request.method} {request.url.path}",
                user_telegram_id=None,
                stack_trace=tb_str,
            )
        except Exception:
            pass

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": "Server ichki xatoligi (Internal Server Error)",
                "detail": str(exc),
                "duration_ms": round(process_time, 2)
            }
        )

    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    # Xavfsizlik sarlavhalari
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    # Keshlanishni oldini olish (Telegram WebApp har doim eng yangi versiyani olishi uchun)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ============================================================
# GLOBAL XATOLIKLARNI QAYTA ISHLASH (EXCEPTION HANDLERS)
# ============================================================

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "status_code": exc.status_code,
        },
        headers=getattr(exc, "headers", None)
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": "Ma'lumotlar validatsiyasida xatolik.",
            "detail": exc.errors(),
            "status_code": 422,
        }
    )


# ============================================================
# SALOMATLIK VA STATUS TEKSHIRUVI (HEALTH CHECK)
# ============================================================

@app.get("/api/health", tags=["System"])
async def health_check() -> Dict[str, Any]:
    """
    API va server holatini tekshiruvchi public endpoint.
    """
    return {
        "status": "ok",
        "game": "The Iron Throne: Xonadonlar Urushi",
        "api_version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# Routerni ulash
app.include_router(player_router)
app.include_router(actions_router)
app.include_router(errors_router)

# Frontend statik fayllarini ulash (Single Page Application)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=False)
