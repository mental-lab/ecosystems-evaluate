FROM cgr.dev/chainguard/python:latest-dev

# Runtime tools the analyzer shells out to (must be installed as root
# before dropping privileges)
USER root
RUN apk add --no-cache git syft

USER 65532
WORKDIR /home/nonroot

# Install the package with a fixed toolchain:
# create venv, upgrade pip/setuptools, then pip-install the project
COPY pyproject.toml README.md /home/nonroot/
COPY repo_analyzer /home/nonroot/repo_analyzer
RUN python -m venv /home/nonroot/venv \
 && /home/nonroot/venv/bin/python -m pip install --no-cache-dir --upgrade "pip>=25.3" "setuptools>=78.1.1" \
 && /home/nonroot/venv/bin/pip install --no-cache-dir /home/nonroot

# Add venv to PATH
ENV PATH="/home/nonroot/venv/bin:${PATH}"

# Allow running as an arbitrary uid (`--user $(id -u):$(id -g)`) so reports
# written to a bind-mounted host dir are owned by the host user
USER root
RUN chmod -R a+rX /home/nonroot
USER 65532

ENTRYPOINT ["ecosystems-evaluate"]
