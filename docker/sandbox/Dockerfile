FROM python:3.10-slim
MAINTAINER sandbox <dmeck@suoxya.com>

WORKDIR /app
# 直接创建源文件而不是复制
RUN rm -rf /etc/apt/sources.list.d/* && \
    echo "deb http://mirrors.aliyun.com/debian bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list && \
    echo "deb http://mirrors.aliyun.com/debian-security bookworm-security main contrib non-free non-free-firmware" > /etc/apt/sources.list.d/security.list && \
    echo "deb http://mirrors.aliyun.com/debian bookworm-updates main contrib non-free non-free-firmware" > /etc/apt/sources.list.d/updates.list && \
    apt-get update
RUN apt install -y vim curl procps gnupg
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# 复制 sandbox 目录到 /app/sandbox
ADD agent_sandbox-0.1.0-py3-none-any.whl /app/sandbox/agent_sandbox-0.1.0-py3-none-any.whl
ADD sandbox.yaml /app/sandbox/sandbox.yaml
RUN ls /app/sandbox
# 设置工作目录
RUN pip install --no-cache-dir /app/sandbox/agent_sandbox-0.1.0-py3-none-any.whl -i https://pypi.tuna.tsinghua.edu.cn/simple

# 创建非 root 用户并预创建 logs 目录
RUN useradd -m -u 1000 -s /bin/bash sandbox && \
    mkdir -p /app/logs && \
    chown -R sandbox:sandbox /app && \
    chmod -R 755 /app
USER sandbox
CMD ["python", "-m","sandbox.start.start", "--speakers-config-file", "/app/sandbox/sandbox.yaml", "--verbose", "--mode", "web"]


EXPOSE 10000