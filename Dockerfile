FROM python:3.13-slim

WORKDIR /app

COPY ./app/requirements.txt .
RUN apt-get update
RUN apt-get install -y tesseract-ocr
RUN pip install --no-cache-dir -r requirements.txt


COPY ./app /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]