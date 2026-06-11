# lab/monitor/Dockerfile — Detection pipeline inside Docker
# This runs the detection pipeline as a containerised monitoring process.

FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies (no training deps needed)
RUN pip install --no-cache-dir \
    scapy \
    pandas \
    numpy \
    scikit-learn \
    joblib \
    tqdm \
    requests

# The actual pipeline code is mounted as a volume from the host.
# This Dockerfile provides only the runtime environment.

CMD ["python3", "-u", "src/pipeline.py", "--help"]
