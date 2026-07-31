ARG VERSION="3.11-bullseye"
FROM mcr.microsoft.com/devcontainers/python:1-${VERSION}

COPY requirements.txt /tmp/pip-tmp/
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r /tmp/pip-tmp/requirements.txt \
    && rm -rf /tmp/pip-tmp

# See https://code.visualstudio.com/remote/advancedcontainers/add-nonroot-user#_change-the-uidgid-of-an-existing-container-user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupmod --gid $USER_GID $USERNAME \
    && usermod --uid $USER_UID --gid $USER_GID $USERNAME \
    && chown -R $USER_UID:$USER_GID /home/$USERNAME
