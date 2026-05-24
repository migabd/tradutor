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

# Self-upgrade yt-dlp to the absolute latest version on start to ensure YouTube changes are always supported
try:
    import subprocess
    import sys
    print("Verificando e atualizando yt-dlp em segundo plano...")
    subprocess.Popen([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except Exception as e:
    print(f"Aviso: Não foi possível atualizar o yt-dlp em segundo plano: {e}")

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
    cookies: str = ""

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
            return {"valid": True, "warning": "Chave aceita, mas a resposta do modelo foi vazia."}
    except Exception as e:
        error_msg = str(e)
        # If the error is a quota/rate limit error, the key IS valid (authenticated successfully by Google, but out of quota)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
            return {
                "valid": True, 
                "warning": "Sua chave de API é válida, mas atingiu temporariamente o limite de cota do Gemini (Erro 429: Resource Exhausted). Você poderá usá-la assim que o limite de tempo expirar."
            }
        return {"valid": False, "error": error_msg}

@app.get("/api/models")
async def list_models(x_gemini_key: str = Header(None, alias="X-Gemini-Key")):
    """List all available Gemini models for the provided API key."""
    if not x_gemini_key:
        raise HTTPException(status_code=400, detail="Gemini API Key é obrigatória.")
        
    try:
        client = genai.Client(api_key=x_gemini_key)
        api_models = []
        for m in client.models.list():
            name = m.name
            display_id = name.replace("models/", "") if name.startswith("models/") else name
            
            # Filter for models containing 'gemini' and that support generating content
            is_gemini = "gemini" in display_id.lower()
            supports_generation = True
            
            # Safe check for supported generation methods
            if hasattr(m, "supported_generation_methods"):
                methods = [method.lower() for method in getattr(m, "supported_generation_methods", [])]
                supports_generation = any("generatecontent" in method for method in methods)
                
            if is_gemini and supports_generation:
                api_models.append({
                    "id": display_id,
                    "name": m.display_name or display_id,
                    "description": m.description or ""
                })
        
        if api_models:
            # Sort the live models nicely
            def sort_key(model):
                mid = model["id"].lower()
                if "gemini-2.5-flash" in mid:
                    return (0, mid)
                elif "gemini-2.0-flash" in mid and "lite" not in mid:
                    return (1, mid)
                elif "gemini-2.0-flash-lite" in mid:
                    return (2, mid)
                elif "gemini-2.0" in mid:
                    return (3, mid)
                elif "gemini-1.5-pro" in mid:
                    return (4, mid)
                elif "gemini-1.5-flash" in mid:
                    return (5, mid)
                return (6, mid)
                
            api_models.sort(key=sort_key)
            return {"models": api_models}
            
    except Exception as e:
        # If API listing fails, we log it and fallback to the standard popular models
        print(f"Aviso: Erro ao obter modelos da API Gemini ({e}). Usando lista padrão de fallback.")
        
    # Standard popular models to guarantee the user always has a rich list if API call fails
    default_models = [
        {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "description": "Modelo padrão mais recente, rápido e inteligente (Recomendado)"},
        {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "description": "Excelente equilíbrio entre velocidade e qualidade"},
        {"id": "gemini-2.0-flash-lite", "name": "Gemini 2.0 Flash-Lite", "description": "Velocidade ultrarrápida com baixo consumo de recursos"},
        {"id": "gemini-2.0-pro-exp-02-05", "name": "Gemini 2.0 Pro (Experimental)", "description": "Modelo experimental de alta performance para tarefas complexas"},
        {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "description": "Altíssima inteligência para raciocínio complexo"},
        {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "description": "Modelo rápido e versátil para tarefas gerais"},
    ]
    
    def sort_key(model):
        mid = model["id"].lower()
        if "gemini-2.5-flash" in mid:
            return (0, mid)
        elif "gemini-2.0-flash" in mid and "lite" not in mid:
            return (1, mid)
        elif "gemini-2.0-flash-lite" in mid:
            return (2, mid)
        elif "gemini-2.0" in mid:
            return (3, mid)
        elif "gemini-1.5-pro" in mid:
            return (4, mid)
        elif "gemini-1.5-flash" in mid:
            return (5, mid)
        return (6, mid)
        
    default_models.sort(key=sort_key)
    return {"models": default_models}


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
        ducking=req.ducking,
        cookies=req.cookies
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
