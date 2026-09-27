FROM python:3.12-slim-bookworm
WORKDIR /app
COPY index.html config.js ./
EXPOSE 3000
# Template config.js from the env var docker-compose already sets, then serve
# the static files with the stdlib — no nginx, no build step, no deps.
CMD ["sh", "-c", "sed -i \"s#http://localhost:8000#${WORKLIST_API_BASE_URL:-http://localhost:8000}#\" config.js; exec python3 -m http.server 3000"]
