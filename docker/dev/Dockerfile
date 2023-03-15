FROM python:3.11.2-slim-bullseye

RUN apt-get update && apt-get install -y postgresql-client git

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

ENV CELERY_ARGS="-A app.project.celery_worker:celery"
CMD C_FORCE_ROOT=1 celery $CELERY_ARGS worker & \
    docker/wait-for-celery.sh "$CELERY_ARGS" \
    docker/wait-for-postgres.sh db "flask run --host=0.0.0.0"