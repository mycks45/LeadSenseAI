from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os

from scrape_agencies import scrape_google_maps

app = FastAPI()

# Make sure we have a templates directory and a static directory
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Mount static for CSS and JS and JSON data
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

class ScrapeRequest(BaseModel):
    location: str
    keyword: str

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/scrape")
async def start_scrape(scrape_request: ScrapeRequest):
    location = scrape_request.location.strip()
    keyword = scrape_request.keyword.strip()
    if not location:
        return {"error": "Location cannot be empty"}
    if not keyword:
        return {"error": "Keyword cannot be empty"}
        
    try:
        data = await scrape_google_maps(location, keyword)
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
