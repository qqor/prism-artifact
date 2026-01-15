FROM ghcr.io/astral-sh/uv:0.7.2 as uv

FROM cruizba/ubuntu-dind:latest

COPY --from=uv /uv /bin/uv
COPY --from=uv /uvx /bin/uvx

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && apt install -y build-essential git libtool python3-dev rsync xxd

RUN git config --global user.email "1@1.com"
RUN git config --global user.name "-"

WORKDIR /app
COPY .venv .venv
COPY pyproject.toml .
COPY uv.lock .
COPY README.md .

COPY third_party ./third_party
COPY wrappers ./wrappers

COPY packages ./packages
COPY scripts ./scripts
RUN uv sync --no-dev --frozen



ENV COLUMNS=200

ENTRYPOINT ["uv", "run", "--no-dev", "--frozen", "python", "scripts/eval/afc_benchmark.py"]
