FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# A porta web e a porta padrão que o flask está rodando via app.py
EXPOSE 5000
CMD ["python", "app.py"]
