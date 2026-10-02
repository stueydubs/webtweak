# Project layer on sandcastle-base. Built with no context, so no COPY.
# webtweak's gates are pytest, and the browser suite drives a real Chromium
# through Playwright. The base image has Python and Node but no browser.
ARG BASE=sandcastle-base:latest
FROM ${BASE}

USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv \
 && python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir pytest playwright \
 && /opt/venv/bin/playwright install --with-deps chromium \
 && chmod -R a+rX /opt/ms-playwright \
 && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/venv/bin:${PATH}
USER agent
