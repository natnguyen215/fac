# Linux environment for running skill2fac (fac needs bash + jq).
# Build from the repo root:  docker build -f skill2fac/Dockerfile -t fac-skill2fac .
# Same setup as the repo's Dockerfile, but with the apt packages inline,
# because a Windows checkout gives packages.txt CRLF line endings that apt can't read.
FROM debian:13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip git jq ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# fac auto-commits builds; the run repos live on a bind mount, so trust every directory
RUN git config --global init.defaultBranch master \
 && git config --global user.email "skill2fac@localhost" \
 && git config --global user.name "skill2fac" \
 && git config --global safe.directory '*'

WORKDIR /fac
COPY requirements.txt /tmp/fac-requirements.txt
COPY skill2fac/requirements.txt /tmp/skill2fac-requirements.txt
RUN pip3 install --break-system-packages \
    -r /tmp/fac-requirements.txt \
    -r /tmp/skill2fac-requirements.txt

# install fac itself
COPY pyproject.toml /fac/
COPY fac /fac/fac/
COPY facd /fac/facd/
ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0
RUN pip3 install . --break-system-packages
