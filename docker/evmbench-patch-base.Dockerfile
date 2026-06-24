# Slim base for Patch grading only — no ploit/codex/agent CLIs.
# Matches upstream evmbench/base layout (AUDIT_DIR, Foundry v1.3.6) without
# the ploit-builder chain that SIGSEGVs under Rosetta on Apple Silicon.
FROM ubuntu:24.04

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV WORKSPACE_BASE=/home \
    AGENT_DIR=/home/agent \
    AUDIT_DIR=/home/agent/audit \
    SUBMISSION_DIR=/home/agent/submission \
    LOGS_DIR=/home/logs \
    FOUNDRY_DIR=/home/agent/.foundry

ENV PATH=$FOUNDRY_DIR/bin:$PATH
ENV HOME=$AGENT_DIR
ENV DEBIAN_FRONTEND=noninteractive
# Ubuntu 24.04 blocks system-wide pip unless opted in; audit Dockerfiles use pip install.
ENV PIP_BREAK_SYSTEM_PACKAGES=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg \
    git python3 python-is-python3 python3-pip \
    unzip \
    build-essential pkg-config libssl-dev \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && corepack enable \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p "$AUDIT_DIR" "$SUBMISSION_DIR" "$LOGS_DIR"

WORKDIR "$AGENT_DIR"

RUN curl -L https://foundry.paradigm.xyz | bash
RUN foundryup --install v1.3.6

RUN git config --global --add safe.directory "$AGENT_DIR" && \
    git config --global --add safe.directory "$AUDIT_DIR" && \
    git config --global user.email "agent@example.com" && \
    git config --global user.name "agent"

CMD ["bash"]
