FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
# Install CPU-only PyTorch first so pip skips the GPU+CUDA bundles (~2GB)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.12.1
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
# Copy installed packages from builder (CUDA-free thanks to index override)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
# Strip doc/include bloat
RUN rm -rf /usr/local/lib/python3.11/site-packages/torch/share \
           /usr/local/lib/python3.11/site-packages/torch/include
COPY app/ ./app/
COPY alembic.ini .
COPY alembic/ ./alembic/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
