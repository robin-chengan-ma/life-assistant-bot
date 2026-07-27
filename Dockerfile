# 使用輕量級 Python 3.11 映像檔
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 防止 Python 產生 .pyc 檔案並開啟 Unbuffered log
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 複製並安裝 dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案原始碼
COPY . .

# 暴露服務 Port（依據你的應用選擇）
EXPOSE 8080

# 啟動指令
CMD ["python", "main.py"]