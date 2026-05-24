import os
import uuid
import asyncio
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, Header, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from google import genai
from utils.dubber import VideoDubber

app = FastAPI(title="Dublador IA Youtube", description="Dublagem automática de vídeos do YouTube usando Gemini 2.0")

# Setup paths
WORKSPACE = Path(__file__).parent.absolute()
STATIC_DIR = WORKSPACE / "static"
OUTPUT_DIR = WORKSPACE / "output"
TASKS_DIR = WORKSPACE / "tasks"

STATIC_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
TASKS_DIR.mkdir(exist_ok=True)

# Schema for requests
class DubRequest(BaseModel):
    url: str
    voice: str = "Puck"  # Puck, Charon, Aoede, Fenrir, Kore
    ducking: bool = True
    model: str = "gemini-2.0-flash"

class RegenerateRequest(BaseModel):
    task_id: str
    segment_id: int
    updated_text: str
    voice: str = "Puck"
    ducking: bool = True

class KeyCheckRequest(BaseModel):
    api_key: str

@app.post("/api/check_key")
async def check_key(req: KeyCheckRequest):
    """Verify if the provided Gemini API key is valid."""
    try:
        client = genai.Client(api_key=req.api_key)
        # Run a tiny model call to check key validity
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents='Hi',
        )
        if response.text:
            return {"valid": True}
        else:
            return {"valid": False, "error": "Resposta vazia do modelo."}
    except Exception as e:
        return {"valid": False, "error": str(e)}

@app.post("/api/dub")
async def start_dubbing(
    req: DubRequest, 
    background_tasks: BackgroundTasks, 
    x_gemini_key: str = Header(None, alias="X-Gemini-Key")
):
    """Start the automatic dubbing pipeline in a background task."""
    if not x_gemini_key:
        raise HTTPException(status_code=400, detail="Gemini API Key é obrigatória no cabeçalho X-Gemini-Key.")
        
    task_id = str(uuid.uuid4())
    
    # Initialize the dubber
    dubber = VideoDubber(api_key=x_gemini_key, workspace_dir=str(WORKSPACE), model_name=req.model)
    
    # Write initial progress status
    dubber._update_status(task_id, "processing", 5, "Iniciando a tarefa de dublagem...")
    
    # Run the pipeline as a background task
    background_tasks.add_task(
        dubber.run_dubbing_pipeline,
        task_id=task_id,
        url=req.url,
        voice_name=req.voice,
        ducking=req.ducking
    )
    
    return {"task_id": task_id, "status": "processing"}

@app.get("/api/status/{task_id}")
async def get_status(task_id: str, x_gemini_key: str = Header(None, alias="X-Gemini-Key")):
    """Get the current progress and details of a dubbing task."""
    if not x_gemini_key:
        raise HTTPException(status_code=400, detail="Gemini API Key é obrigatória.")
        
    dubber = VideoDubber(api_key=x_gemini_key, workspace_dir=str(WORKSPACE))
    status_data = dubber.get_task_status(task_id)
    return JSONResponse(content=status_data)

@app.post("/api/regenerate_segment")
async def regenerate_segment(
    req: RegenerateRequest,
    background_tasks: BackgroundTasks,
    x_gemini_key: str = Header(None, alias="X-Gemini-Key")
):
    """Regenerate a single dubbing segment and update the dubbed video in the background."""
    # Read the task's model_name if available, default to gemini-2.0-flash
    model_name = "gemini-2.0-flash"
    try:
        import json
        task_file = TASKS_DIR / f"{req.task_id}.json"
        if task_file.exists():
            with open(task_file, "r", encoding="utf-8") as f:
                task_data = json.load(f)
                model_name = task_data.get("model_name", "gemini-2.0-flash")
    except Exception:
        pass

    dubber = VideoDubber(api_key=x_gemini_key, workspace_dir=str(WORKSPACE), model_name=model_name)
    
    # Trigger regeneration in background to avoid client timeout
    background_tasks.add_task(
        dubber.regenerate_single_segment,
        task_id=req.task_id,
        segment_id=req.segment_id,
        updated_text=req.updated_text,
        voice_name=req.voice,
        ducking=req.ducking
    )
    
    return {"status": "processing", "message": "Regeneração do segmento iniciada."}

@app.get("/api/download/{task_id}")
async def download_video(task_id: str):
    """Download the final dubbed video file."""
    video_path = OUTPUT_DIR / f"{task_id}_dubbed.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Vídeo dublado não encontrado ou ainda está em processamento.")
    return FileResponse(path=video_path, media_type="video/mp4", filename=f"dublado_{task_id}.mp4")

@app.get("/api/download_original/{task_id}")
async def download_original_video(task_id: str):
    """Download the cached original video file."""
    video_path = OUTPUT_DIR / f"{task_id}_original.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Vídeo original não encontrado.")
    return FileResponse(path=video_path, media_type="video/mp4", filename=f"original_{task_id}.mp4")

# Mount the static files to serve the frontend interface
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Start uvicorn server on port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)
