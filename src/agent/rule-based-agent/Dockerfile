FROM mcr.microsoft.com/mirror/docker/library/python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl openssh-client && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rule_agent.py .

# Standardizing on root for the demo to ensure SSH key access
USER root

EXPOSE 5001

CMD ["python", "rule_agent.py"]
