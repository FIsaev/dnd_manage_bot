# Long polling needs no inbound port, so this image runs as a plain worker on
# any host. Set WEBHOOK_URL (see README) only where an open port is required.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY dice.py bot.py ./

RUN useradd --create-home --uid 10001 bot
USER bot

# BOT_TOKEN comes from the environment at run time, never baked into the image.
CMD ["python", "bot.py"]
