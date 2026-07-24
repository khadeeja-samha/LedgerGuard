FROM python:3.11-slim

# Install Node.js 20.x, build tools, and native compilation dependencies for Hardhat & crypto packages (secp256k1, keccak)
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    build-essential \
    python3 \
    make \
    g++ \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Install Node dependencies in the blockchain directory for Hardhat smart contract deployment/exploit execution
RUN cd blockchain && npm install

# MANDATORY / NON-NEGOTIABLE: --workers MUST be set to 1.
# The pipeline_lock in app/api/audit.py is an in-process Python lock (asyncio.Lock / threading.Lock).
# Spawning multiple workers creates separate OS processes with isolated memory spaces, breaking the lock
# and reintroducing Hardhat filesystem race conditions during concurrent audits.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
