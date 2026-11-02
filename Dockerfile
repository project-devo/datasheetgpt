FROM python:3.11-slim

# Hugging Face runs the container as user 1000, so create that user
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

# Install packages first, so code changes don't reinstall everything
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the embedding model now, during the build
ENV FASTEMBED_CACHE_PATH=/home/user/app/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

COPY --chown=user . .

EXPOSE 7860
CMD ["uvicorn", "main:app", "--app-dir", "api", "--host", "0.0.0.0", "--port", "7860"]