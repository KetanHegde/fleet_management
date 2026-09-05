FROM python:3.12-slim

WORKDIR /app

COPY robots/requirements.txt /app/robots/requirements.txt
RUN pip install --no-cache-dir -r /app/robots/requirements.txt

COPY robots /app/robots
COPY data /app/data

CMD ["python", "-m", "robots.simulator"]
