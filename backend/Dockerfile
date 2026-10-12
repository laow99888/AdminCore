# AdminCore 后端镜像
# Python 补丁版本与 版本要求.md 基线一致
FROM python:3.13.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_ENV=production

WORKDIR /app

# 系统依赖（psycopg2-binary 无需编译，curl 用于容器健康检查）
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 依赖单独一层，充分利用构建缓存（lock 含 gunicorn/whitenoise 等全部依赖）
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY . .

# 构建期收集静态文件（不依赖数据库；production settings 要求显式 key）
RUN DJANGO_SECRET_KEY=build-time-key python manage.py collectstatic --noinput

EXPOSE 8000

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
