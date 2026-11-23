FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir requests warcio tqdm wacz

COPY *.py .

ENTRYPOINT ["python", "main.py"]