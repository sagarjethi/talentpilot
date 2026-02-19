FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Install PDM
RUN pip install --no-cache-dir pdm

# Copy dependency metadata first for layer caching
COPY pyproject.toml ./
RUN pdm install --prod --no-lock --no-self

# Copy source code
COPY src/ src/
COPY settings.yaml responses.yaml ./

# Install the project itself
RUN pdm install --prod --no-lock

# Install Playwright browsers
RUN pdm run python -m playwright install chromium

CMD ["pdm", "run", "start"]
