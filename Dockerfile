# syntax=docker/dockerfile:1.7-labs
ARG BASE_IMAGE=contract-extractor/api-base:cu130
FROM ${BASE_IMAGE}

WORKDIR /opt/app

COPY api/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r /tmp/requirements.txt

COPY api/app /opt/app/app

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
