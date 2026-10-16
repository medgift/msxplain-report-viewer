# Build OHIF with the /viewer/ subpath baked into webpack's publicPath, so the
# viewer can be served SAME-ORIGIN under https://<host>/viewer/. Same-origin is
# required: it's what lets the viewer share the login session cookie the backend
# DICOMweb proxy (/api/dicom-web) checks. The stock ohif/app image is built with
# PUBLIC_URL=/ and cannot be re-based at runtime (its lazy-loaded WASM/worker
# chunks would 404 from the root), which is why we rebuild here.
#
# First build is slow (clones + builds OHIF from source). It is cached as an
# image tag afterwards, so `docker compose up` only pays it once.
ARG OHIF_VERSION=v3.13.12

# OHIF >= 3.10 builds with Node 24 + pnpm (pinned to the repo's packageManager).
FROM node:24.15.0-bookworm-slim AS builder
ARG OHIF_VERSION
RUN apt-get update \
 && apt-get install -y --no-install-recommends git python3 build-essential ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN npm install -g pnpm@12.8.1
WORKDIR /src
RUN git clone --depth 1 --branch ${OHIF_VERSION} https://github.com/OHIF/Viewers.git .
RUN pnpm install --frozen-lockfile
# ── Local patches (each fails the build if its target text is gone, so an
# OHIF/cornerstone bump can't silently drop them) ──────────────────────────
# 1. cornerstone adapters bug: calculateCentroid() unflattens the SEG pixel
#    index with Rows instead of Columns. On non-square frames (our T1 SEGs are
#    256x240) every segment centre is wrong, so clicking a lesion in the
#    segmentation panel jumps to the wrong place. Still unfixed upstream.
RUN set -e; \
    # OHIF uses pnpm's node-linker=hoisted (no node_modules/.pnpm), so look in
    # every node_modules: root plus any workspace package with its own copy.
    files=$(find . -path '*/node_modules/@cornerstonejs/adapters/dist/esm/adapters/Cornerstone/Segmentation_4X.js' -not -path './.git/*'); \
    echo "Patching: $files"; \
    test -n "$files"; \
    for f in $files; do \
      grep -q 'bufferIndex / multiframe.Rows' "$f"; \
      sed -i 's#bufferIndex / multiframe\.Rows#bufferIndex / multiframe.Columns#; s#bufferIndex % multiframe\.Rows#bufferIndex % multiframe.Columns#' "$f"; \
    done
# 2. Give the MPR protocol's "MPR Reformat 1x3" stage an id, so the report can
#    open it with ?hangingProtocolId=mpr&stageId=mprReformat. That stage aligns
#    the three views to the scan's own orientation instead of the scanner axes,
#    so oblique acquisitions aren't shown slightly rotated.
RUN set -e; \
    f=extensions/cornerstone/src/hps/mpr.ts; \
    grep -q "name: 'MPR Reformat 1x3'," "$f"; \
    sed -i "s#^\( *\)name: 'MPR Reformat 1x3',#\1id: 'mprReformat',\n\1name: 'MPR Reformat 1x3',#" "$f"; \
    grep -q "id: 'mprReformat'," "$f"
# The base path everything is served under. OHIF uses PUBLIC_URL for the
# bundler's publicPath (chunk loading), the app-config.js script src, and the
# default router basename — so this single var re-bases the whole app to /viewer/.
ENV PUBLIC_URL=/viewer/
# APP_CONFIG only sets the DEFAULT baked config; we override app-config.js at
# runtime via a volume mount, so this just needs to be a valid config to build.
ENV APP_CONFIG=config/default.js
# Same as upstream's Dockerfile: skips the slow production-only extras.
ENV QUICK_BUILD=true
RUN pnpm run build

FROM nginx:1.27-alpine
# OHIF is a SPA: unknown paths must fall back to index.html so deep links like
# /viewer/viewer?StudyInstanceUIDs=... resolve. (The frontend nginx strips the
# /viewer/ prefix before proxying here, so this server sees paths at its root.)
RUN printf 'server {\n  listen 80;\n  root /usr/share/nginx/html;\n  location / {\n    try_files $uri $uri/ /index.html;\n  }\n}\n' \
      > /etc/nginx/conf.d/default.conf
COPY --from=builder /src/platform/app/dist /usr/share/nginx/html
