# Build OHIF with the /viewer/ subpath baked into webpack's publicPath, so the
# viewer can be served SAME-ORIGIN under https://<host>/viewer/. Same-origin is
# required: it's what lets the viewer share the login session cookie the backend
# DICOMweb proxy (/api/dicom-web) checks. The stock ohif/app image is built with
# PUBLIC_URL=/ and cannot be re-based at runtime (its lazy-loaded WASM/worker
# chunks would 404 from the root), which is why we rebuild here.
#
# First build is slow (clones + builds OHIF from source). It is cached as an
# image tag afterwards, so `docker compose up` only pays it once.
ARG OHIF_VERSION=v3.9.0

FROM node:18.20.4-bookworm-slim AS builder
ARG OHIF_VERSION
RUN apt-get update \
 && apt-get install -y --no-install-recommends git python3 build-essential ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 --branch ${OHIF_VERSION} https://github.com/OHIF/Viewers.git .
ENV NODE_OPTIONS=--max-old-space-size=8192
RUN yarn config set network-timeout 600000 && yarn install --frozen-lockfile
# The base path everything is served under. OHIF uses PUBLIC_URL for webpack's
# publicPath (chunk loading), the app-config.js script src, and the default
# router basename — so this single var re-bases the whole app to /viewer/.
ENV PUBLIC_URL=/viewer/
# APP_CONFIG only sets the DEFAULT baked config; we override app-config.js at
# runtime via a volume mount, so this just needs to be a valid config to build.
ENV APP_CONFIG=config/default.js
RUN yarn run build

FROM nginx:1.27-alpine
# OHIF is a SPA: unknown paths must fall back to index.html so deep links like
# /viewer/viewer?StudyInstanceUIDs=... resolve. (The frontend nginx strips the
# /viewer/ prefix before proxying here, so this server sees paths at its root.)
RUN printf 'server {\n  listen 80;\n  root /usr/share/nginx/html;\n  location / {\n    try_files $uri $uri/ /index.html;\n  }\n}\n' \
      > /etc/nginx/conf.d/default.conf
COPY --from=builder /src/platform/app/dist /usr/share/nginx/html
