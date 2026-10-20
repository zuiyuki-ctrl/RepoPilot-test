# Supply a verified local Python 3.11 image; no dependency installation or network needed.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY agent.py /agent/minifix.py
USER 10001:10001
WORKDIR /workspace
ENTRYPOINT ["python", "-I", "/agent/minifix.py"]
