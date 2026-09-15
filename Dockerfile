FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
# torch en version CPU uniquement (beaucoup plus léger que la version CUDA
# par défaut) : on l'installe d'abord avec l'index PyTorch dédié, puis le
# reste des dépendances normalement.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
