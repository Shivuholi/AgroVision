from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from . import models
from .database import engine
from .routers import sensors, control, weather
from .services.control_loop import run_control_loop

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Smart Agriculture Digital Twin API")

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sensors.router)
app.include_router(control.router)
app.include_router(weather.router)

@app.on_event("startup")
async def startup_event():
    # Start the control loop background task
    asyncio.create_task(run_control_loop())

@app.get("/")
def read_root():
    return {"message": "Welcome to the Smart Agriculture API"}
