from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import os
import shutil
import uuid
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Date, ForeignKey
from celery import Celery
import pytesseract
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Document Processor API",
    description="API for uploading, analyzing and managing documents",
    version="1.0.0"
)

from database import SessionLocal, Base, engine


celery = Celery(
    'tasks',
    broker=os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//"),
    backend='rpc://'
)


DATABASE_URL = "postgresql://elenacuprova:root@db:5432/postgres"

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    psth = Column(String)
    date = Column(Date)


class DocumentText(Base):
    __tablename__ = "documents_text"
    id = Column(Integer, primary_key=True, index=True)
    id_doc = Column(Integer, ForeignKey('documents.id'))
    text = Column(String)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@celery.task
def process_document(doc_id: int, image_path: str):
    try:
        text = pytesseract.image_to_string(Image.open(image_path))
        db = SessionLocal()
        doc_text = DocumentText(id_doc=doc_id, text=text)
        db.add(doc_text)
        db.commit()
        db.close()
        return {"status": "success", "doc_id": doc_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/upload_doc", response_model=dict)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        os.makedirs("documents", exist_ok=True)
        file_name = f"{uuid.uuid4()}.jpg"
        file_path = os.path.join("documents", file_name)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        doc = Document(psth=file_path, date=date.today())
        db.add(doc)
        db.commit()
        db.refresh(doc)

        return {"id": doc.id, "path": file_path, "date": doc.date}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/doc_delete/{doc_id}", summary="Delete a document")
async def delete_document(doc_id: int):
    try:
        db = SessionLocal()
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if os.path.exists(doc.psth):
            os.remove(doc.psth)

        db.query(DocumentText).filter(DocumentText.id_doc == doc_id).delete()
        db.delete(doc)
        db.commit()
        db.close()

        return {"message": "Document deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/doc_analyse/{doc_id}", summary="Analyze document text")
async def analyze_document(doc_id: int):
    try:
        db = SessionLocal()
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        task = process_document.delay(doc_id, doc.psth)
        return {"message": "Analysis started", "task_id": task.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_text/{doc_id}", summary="Get extracted text")
async def get_text(doc_id: int):
    try:
        db = SessionLocal()
        doc_text = db.query(DocumentText).filter(DocumentText.id_doc == doc_id).first()
        if not doc_text:
            raise HTTPException(status_code=404, detail="Text not found")

        return {"text": doc_text.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

