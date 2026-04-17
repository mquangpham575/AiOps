FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl openssh-client && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py tools.py ./

# Standardizing on root for the demo to ensure SSH key access and sudo execution capability
USER root

EXPOSE 8080

CMD ["python", "agent.py"]
