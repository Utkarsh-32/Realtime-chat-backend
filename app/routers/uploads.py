from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import uuid

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = "media"

@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(400, "No file uploaded")

    if file.filename is None:
        raise HTTPException(400, "Filename missing")
    
    if file.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(400, "Only JPG and PNG allowed")
    
    ext = file.filename.split(".")[-1]
    new_name = f"{uuid.uuid4()}.{ext}"

    save_path = os.path.join(UPLOAD_DIR, new_name)

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    return {
        "filename": new_name,
        "url": f"/media/{new_name}"
    }