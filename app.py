from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
import csv

from scrape_agencies import scrape_google_maps
import database
from datetime import datetime

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

class BulkStageRequest(BaseModel):
    ids: List[int]
    stage: int

class UpdatePhoneRequest(BaseModel):
    phone: str

class UpdateStageRequest(BaseModel):
    stage: int

class UpdateEmailRequest(BaseModel):
    email: str

class ContactRequest(BaseModel):
    timestamp: str

class AddRemarkRequest(BaseModel):
    stage: int
    text: str

class AddLeadRequest(BaseModel):
    name: str
    phone: str
    email: str
    website: str = ""
    location: str = ""

class TemplateRequest(BaseModel):
    content: str

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/scrape")
async def start_scrape(scrape_request: ScrapeRequest, background_tasks: BackgroundTasks):
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

    async def run_scrape():
        try:
            data = await scrape_google_maps(location, keyword, log_callback)
            ws = active_sockets.get(client_id)
            if ws:
                if data and data.get("results"):
                    import json
                    payload = json.dumps({"results": data["results"], "filename": data["filename"], "count": len(data["results"])})
                    await ws.send_text(f"SCRAPE_COMPLETE:{payload}")
                else:
                    await ws.send_text("SCRAPE_COMPLETE:{\"error\": \"No results found.\"}")
        except Exception as e:
            import traceback
            err_detail = traceback.format_exc()
            print(f"[SCRAPE ERROR] {err_detail}")
            ws = active_sockets.get(client_id)
            if ws:
                import json
                await ws.send_text(f"SCRAPE_COMPLETE:{json.dumps({'error': str(e)})}")

    background_tasks.add_task(run_scrape)
    return {"success": True, "status": "started", "job_id": client_id}

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

@app.post("/api/leads/bulk_stage")
def api_bulk_stage(req: BulkStageRequest):
    try:
        database.bulk_update_stage(req.ids, req.stage)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/download_filtered")
def download_filtered_leads(stage: int):
    try:
        leads = database.get_leads_by_stage(stage)
        if not leads:
            return {"error": "No leads found for this stage."}
        stage_names = ["Uncontacted", "Contacted", "Pitched", "MOU_Sent", "MOU_Signed", "Toolkit_Sent", "Onboarded"]
        stage_label = stage_names[stage] if stage < len(stage_names) else f"Stage_{stage}"
        filename = f"leadsense_stage_{stage}_{stage_label}.csv"
        filepath = os.path.join(os.getcwd(), filename)
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=leads[0].keys())
            writer.writeheader()
            writer.writerows(leads)
        return FileResponse(path=filepath, filename=filename, media_type='text/csv')
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/leads")
def api_add_manual_lead(req: AddLeadRequest):
    try:
        database.add_manual_lead(req.name, req.phone, req.email, req.website, req.location)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/templates/{template_id}")
def api_get_template(template_id: str):
    try:
        return {"success": True, "content": database.get_template(template_id)}
    except Exception as e:
        return {"error": str(e)}

@app.put("/api/templates/{template_id}")
def api_save_template(template_id: str, req: TemplateRequest):
    try:
        database.save_template(template_id, req.content)
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

# --- CRM Endpoints ---

@app.get("/crm/{lead_id}", response_class=HTMLResponse)
async def view_crm_lead(request: Request, lead_id: int):
    # Pass basic param down, rest handled via API or jinja if needed
    return templates.TemplateResponse("crm_view.html", {"request": request, "lead_id": lead_id})

@app.get("/api/leads/{lead_id}")
def api_get_lead(lead_id: int):
    try:
        lead = database.get_lead_by_id(lead_id)
        if lead is None:
            return {"error": "Lead not found"}
        
        remarks = database.get_remarks_for_lead(lead_id)
        return {"success": True, "lead": lead, "remarks": remarks}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/leads/{lead_id}/remarks")
def api_add_remark(lead_id: int, req: AddRemarkRequest):
    try:
        database.add_remark(lead_id, req.stage, req.text)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/leads/{lead_id}/stage")
def api_update_stage(lead_id: int, req: UpdateStageRequest):
    try:
        database.update_lead_stage(lead_id, req.stage)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

@app.put("/api/leads/{lead_id}/mou_email")
def api_update_mou_email(lead_id: int, req: UpdateEmailRequest):
    try:
        database.update_mou_email(lead_id, req.email)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/leads/{lead_id}/contact")
def api_update_contact(lead_id: int, req: ContactRequest):
    try:
        database.update_last_contacted(lead_id, req.timestamp)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/leads/{lead_id}/send_mou")
def api_send_mou(lead_id: int):
    # Dummy Email logic for MOU
    try:
        lead = database.get_lead_by_id(lead_id)
        email_to = lead.get('mou_email') or lead.get('email')
        if not email_to:
            return {"error": "No email address found to send MOU."}
        
        # MOCK SMTP Logic
        print(f"[MOCK EMAIL] Sending MOU to {email_to} for lead {lead.get('name')}")
        # When ready, user can configure smtplib here:
        # server = smtplib.SMTP('smtp.gmail.com', 587) ...
        
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/leads/{lead_id}/send_toolkit")
def api_send_toolkit(lead_id: int):
    # Dummy Email logic for Toolkit
    try:
        lead = database.get_lead_by_id(lead_id)
        email_to = lead.get('mou_email') or lead.get('email')
        if not email_to:
            return {"error": "No email address found to send Toolkit."}
        
        # MOCK SMTP Logic
        print(f"[MOCK EMAIL] Sending Toolkits and Ack to {email_to} for lead {lead.get('name')}")
        
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

