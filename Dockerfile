# Campus Market in one container. Build and start it with
#
#     docker compose up --build
#
# and open http://127.0.0.1:8000. The README says more.

# 3.12, the same Python as CI and the README.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CAMPUS_DB=/data/campus.db \
    CAMPUS_SEED=1 \
    FORWARDED_ALLOW_IPS=*

WORKDIR /app

# Requirements on their own first, so changing code does not reinstall them.
# --require-hashes, so the image installs exactly the packages that were
# audited and nothing that was swapped on the way.
COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt

COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# The server does not run as root. The two folders it writes to belong to it,
# and a fresh volume mounted on either takes over that owner.
RUN useradd --system --uid 10001 --home-dir /app campus \
 && mkdir -p /data app/static/uploads \
 && chown -R campus:campus /data app/static/uploads \
 && chmod +x /usr/local/bin/docker-entrypoint.sh
USER campus

VOLUME ["/data", "/app/app/static/uploads"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/login', timeout=4)"

ENTRYPOINT ["docker-entrypoint.sh"]
# --proxy-headers lets uvicorn believe the https proxy in front about the
# scheme. Which proxies it believes comes from FORWARDED_ALLOW_IPS above,
# which uvicorn reads itself. Inside Docker the proxy never arrives from
# 127.0.0.1, so the default would ignore it and the origin check would refuse
# every form with "Request origin refused". The port is only published on
# the host's 127.0.0.1 (compose.yaml), so the proxy is the only thing that
# can reach it and trusting every sender is safe.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
