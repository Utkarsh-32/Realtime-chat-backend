import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth_service import get_current_user

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = "media"
logger = logging.getLogger(__name__)


@router.post("/image")
async def upload_image(file: UploadFile = File(...), user=Depends(get_current_user)):
    if not user:
        logger.warning("User not authenticated", exc_info=True)
        raise HTTPException(401, "Not allowed")
    if not file:
        logger.warning("File not provided", exc_info=True)
        raise HTTPException(400, "No file uploaded")

    if file.filename is None:
        logger.warning("File name not provided", exc_info=True)
        raise HTTPException(400, "Filename missing")

    if file.content_type not in ["image/jpeg", "image/png"]:
        logger.warning("Only JPG & PNG allowed", exc_info=True)
        raise HTTPException(400, "Only JPG and PNG allowed")

    ext = file.filename.split(".")[-1]
    new_name = f"{uuid.uuid4()}.{ext}"

    save_path = os.path.join(UPLOAD_DIR, new_name)

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    logger.info("Image uploaded")
    return {"filename": new_name, "url": f"/media/{new_name}"}
