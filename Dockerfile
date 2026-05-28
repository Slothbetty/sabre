FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app/src
CMD ["python", "run_comparison.py", \
     "-n", "synthetic/network.json", \
     "-m", "synthetic/movie.json", \
     "-sc", "synthetic/seeks.json,synthetic/seeks_prefetch_hit.json,synthetic/seeks_mixed.json,synthetic/seeks_linear_hit_nonlinear_miss.json,synthetic/seeks_linear_miss_nonlinear_hit.json", \
     "-pc", "synthetic/test_prefetch_config.json", \
     "-a", "all", \
     "-o", "synthetic/results"]
