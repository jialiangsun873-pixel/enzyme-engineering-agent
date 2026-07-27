# ============================================================
# GROMACS MCP Server — Docker 镜像
# ============================================================
# 基础: miniconda3 → GROMACS 2024 → MDAnalysis → FastMCP
# 用途: 把 GROMACS MD 管线暴露为 MCP 接口, 供 AI Agent 调用
#
# 构建:
#   docker build -t gromacs-mcp .
#   docker compose build
#
# 运行 (MCP 模式, stdio):
#   docker run --rm -i -v "$(pwd)/data:/data" gromacs-mcp
#
# 运行 (交互调试):
#   docker run --rm -it -v "$(pwd)/data:/data" gromacs-mcp bash
# ============================================================

FROM continuumio/miniconda3:latest

# ── 元数据 ──────────────────────────────────────────
LABEL org.opencontainers.image.title="GROMACS MCP Server"
LABEL org.opencontainers.image.description="GROMACS 2024 + MDAnalysis, exposed as MCP tools for MD simulation pipelines"
LABEL org.opencontainers.image.version="1.0"
LABEL org.opencontainers.image.gromacs="2024"

# ── 系统依赖 ────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libx11-6 \
    libxrender1 \
    libxext6 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ── GROMACS + Python 科学计算栈 ─────────────────────
# 放一层: 利用 Docker 缓存, 代码变了这层不用重装
RUN conda install -c conda-forge -y \
    python=3.12 \
    gromacs=2024 \
    mdanalysis \
    numpy \
    pandas \
    matplotlib \
    && conda clean -a -y

# ── MCP 框架 ───────────────────────────────────────
RUN pip install --no-cache-dir fastmcp loguru

# ── 验证安装 ───────────────────────────────────────
RUN gmx --version 2>&1 | head -3 && \
    python -c "import MDAnalysis; print('MDAnalysis', MDAnalysis.__version__)" && \
    python -c "import fastmcp; print('FastMCP OK')"

# ── 服务器代码 ─────────────────────────────────────
COPY server.py /app/server.py
RUN chmod +r /app/server.py

# ── 运行时 ─────────────────────────────────────────
WORKDIR /data
ENTRYPOINT ["python", "/app/server.py"]
