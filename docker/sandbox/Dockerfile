FROM python:3.10-slim
MAINTAINER sandbox <dmeck@suoxya.com>

WORKDIR /app
# 直接创建源文件而不是复制
RUN rm -rf /etc/apt/sources.list.d/* && \
    echo "deb http://mirrors.aliyun.com/debian bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list && \
    echo "deb http://mirrors.aliyun.com/debian-security bookworm-security main contrib non-free non-free-firmware" > /etc/apt/sources.list.d/security.list && \
    echo "deb http://mirrors.aliyun.com/debian bookworm-updates main contrib non-free non-free-firmware" > /etc/apt/sources.list.d/updates.list && \
    apt-get update
RUN apt install -y vim
RUN apt install -y curl
RUN apt install -y procps

# 复制 sandbox 目录到 /app/sandbox
ADD agent_sandbox-0.1.0-py3-none-any.whl /app/sandbox/agent_sandbox-0.1.0-py3-none-any.whl
ADD sandbox.yaml /app/sandbox/sandbox.yaml
RUN ls /app/sandbox
# 设置工作目录
RUN pip install --no-cache-dir /app/sandbox/agent_sandbox-0.1.0-py3-none-any.whl -i https://pypi.tuna.tsinghua.edu.cn/simple
CMD ["python", "-m","sandbox.start.start", "--speakers-config-file", "/app/sandbox/sandbox.yaml", "--verbose", "--mode", "web"]


EXPOSE 10000