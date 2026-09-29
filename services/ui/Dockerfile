FROM node:22-alpine AS build
WORKDIR /ui
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=build /ui/dist ./
EXPOSE 3000
# Template config.js from the env var docker-compose already sets, then serve
# the built files with the stdlib -- no nginx. Hash routing needs no rewrites.
CMD ["sh", "-c", "sed -i \"s#http://localhost:8000#${WORKLIST_API_BASE_URL:-http://localhost:8000}#\" config.js; exec python3 -m http.server 3000"]
