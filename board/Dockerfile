# SPDX-License-Identifier: Apache-2.0
#
# The board's explainer, served alone where no plane runs (docs/adr/0035,
# amended 2026-11-02): Cloud Run, or any container host. Named Dockerfile,
# not Containerfile like the rest of the repo, because `gcloud run deploy
# --source board/` builds only a file with that name. Same Python digest as
# app/backend and workloads/minimal. Build context is ./board.
FROM docker.io/library/python:3.13-slim-trixie@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285
WORKDIR /srv
COPY index.html serve.py board/
ENV BOARD_STATIC=1 PYTHONUNBUFFERED=1
USER 65534
EXPOSE 8080
CMD ["python3", "board/serve.py"]
