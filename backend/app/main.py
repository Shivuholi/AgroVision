from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from . import models
from .database import engine
from .routers import sensors, control, weather
from .services.control_loop import run_control_loop
from .services.mqtt_service import start_mqtt_service, stop_mqtt_service

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Smart Agriculture IoT Irrigation API")

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sensors.router)
app.include_router(control.router)
app.include_router(weather.router)

@app.on_event("startup")
async def startup_event():
    # 1. Start the real-time MQTT bridge service (<50ms latency)
    start_mqtt_service()
    # 2. Start the periodic control loop background task
    asyncio.create_task(run_control_loop())

@app.on_event("shutdown")
def shutdown_event():
    stop_mqtt_service()

@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Welcome to the Smart Agriculture API (Real-Time MQTT & HTTP Enabled)"
    }
