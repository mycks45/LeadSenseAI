from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
import uuid
import csv

from scrape_agencies import scrape_google_maps
import database

app = FastAPI()

active_sockets: dict = {}

@app.websocket("/ws/scrape/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_sockets[client_id] = websocket
    try:
        while True:
            # We don't expect messages from client, just keeping it alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        if client_id in active_sockets:
            del active_sockets[client_id]

# Make sure we have a templates directory and a static directory
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Mount static for CSS and JS and JSON data
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

class ScrapeRequest(BaseModel):
    location: str
    keyword: str
    client_id: str

from typing import List
class BulkDeleteRequest(BaseModel):
    ids: List[int]

class UpdatePhoneRequest(BaseModel):
    phone: str

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/scrape")
async def start_scrape(scrape_request: ScrapeRequest):
    location = scrape_request.location.strip()
    keyword = scrape_request.keyword.strip()
    client_id = scrape_request.client_id
    
    if not location:
        return {"error": "Location cannot be empty"}
    if not keyword:
        return {"error": "Keyword cannot be empty"}
        
    async def log_callback(msg: str):
        ws = active_sockets.get(client_id)
        if ws:
            try:
                await ws.send_text(msg)
            except Exception:
                pass
                
    try:
        data = await scrape_google_maps(location, keyword, log_callback)
        if not data or not data.get("filename"):
            return {"error": "Failed to scrape any data or zero results found."}
            
        return {
            "success": True,
            "results": data["results"],
            "filename": data["filename"],
            "count": len(data["results"])
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join(os.getcwd(), filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=filename, media_type='text/csv')
    return {"error": "File not found"}

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/leads")
def api_get_leads():
    try:
        leads = database.get_all_leads()
        return {"success": True, "leads": leads}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/download_all")
def download_all_leads():
    try:
        leads = database.get_all_leads()
        if not leads:
            return {"error": "No leads in database."}
            
        filename = "leadsense_master_export.csv"
        filepath = os.path.join(os.getcwd(), filename)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=leads[0].keys())
            writer.writeheader()
            writer.writerows(leads)
            
        return FileResponse(path=filepath, filename=filename, media_type='text/csv')
    except Exception as e:
        return {"error": str(e)}

@app.delete("/api/leads/{lead_id}")
def api_delete_lead(lead_id: int):
    try:
        database.delete_lead(lead_id)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/leads/delete_bulk")
def api_delete_bulk(req: BulkDeleteRequest):
    try:
        database.delete_leads_bulk(req.ids)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

@app.put("/api/leads/{lead_id}/phone")
def api_update_phone(lead_id: int, req: UpdatePhoneRequest):
    try:
        database.update_lead_phone(lead_id, req.phone)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

