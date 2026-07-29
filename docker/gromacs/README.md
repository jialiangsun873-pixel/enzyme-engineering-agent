# GROMACS MCP Server — Docker 镜像

[![GROMACS](https://img.shields.io/badge/GROMACS-2024.5-blue)](https://www.gromacs.org/)
[![Python](https://img.shields.io/badge/Python-3.12-green)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-brightgreen)](https://www.docker.com/)
[![CUDA](https://img.shields.io/badge/CUDA-12.5-76b900)](https://developer.nvidia.com/cuda-toolkit)

**把 GROMACS MD 管线暴露为 MCP 工具接口，Docker 一键部署，供 AI Agent 调用。**

---

## 内置工具 (MCP Tools)

| 阶段 | 工具 | 说明 |
|---|---|---|
| 准备 | `pdb2gmx` | PDB → GROMACS 拓扑文件 |
| 准备 | `solvate` | 加水盒子 |
| 准备 | `add_ions` | 加离子中和体系电荷 |
| 运行 | `energy_minimize` | 能量最小化 (steepest descent) |
| 运行 | `run_nvt` | NVT 系综平衡 (恒温恒容) |
| 运行 | `run_npt` | NPT 系综平衡 (恒温恒压) |
| 运行 | `production_md` | 生产 MD 模拟 (GPU 自动加速) |
| 分析 | `analyze_rmsd` | 轨迹 RMSD 分析 |
| 分析 | `analyze_rmsf` | 残基 RMSF 柔性分析 |
| 分析 | `analyze_hbonds` | 氢键数量及 occupancy 分析 |
| 调试 | `echo_test` | Echo 测试 |
| 调试 | `gpu_info` | GPU 可用性检测 |

**MD 工作流:** `pdb2gmx → solvate → add_ions → energy_minimize → run_nvt → run_npt → production_md → analyze`

---

## 快速开始

### 方式一：预构建镜像（推荐）

```bash
# CPU 版 — 任意机器
docker pull ghcr.io/jialiangsun873-pixel/gromacs-mcp:2024

# GPU 版 — NVIDIA GPU + nvidia-container-toolkit
docker pull ghcr.io/jialiangsun873-pixel/gromacs-mcp:2024-gpu

┌──────────┬─────────────────────────────┬────────┬───────┬───────────────────────────────────────────────────────┐
│   Tag    │           GROMACS           │  加速  │ 大小  │                       环境要求                        │
├──────────┼─────────────────────────────┼────────┼───────┼─────────────────────────────
│ 2024     │ 2024 (CPU)                  │ —      │ ~5 GB │ Docker                                                │
├──────────┼─────────────────────────────┼────────┼───────┼─────────────────────────────
│ 2024-gpu │ 2024.5 源码编译 (CUDA SM89) │ 10-50x │ ~8 GB │ Docker + NVIDIA 驱动 ≥ 555 + nvidia-container-toolkit │
└──────────┴─────────────────────────────┴────────┴───────┴───────────────────────────────────────────────────────┘

方式二：自行构建

git clone https://github.com/jialiangsun873-pixel/enzyme-engineering-agent.git
cd enzyme-engineering-agent/engine/enzyme_lab/mcp_servers/gromacs

# CPU 版
docker compose build gromacs

# GPU 版
docker compose build gromacs-gpu

---
使用方法

MCP 模式（AI Agent 调用）

容器通过 stdio 走 MCP JSON-RPC 协议，Agent 工具层直接 docker run -i 通信：

# CPU
docker run --rm -i -v $(pwd)/data:/data ghcr.io/jialiangsun873-pixel/gromacs-mcp:2024

# GPU
docker run --rm -i --gpus all -v $(pwd)/data:/data ghcr.io/jialiangsun873-pixel/gromacs-

交互调试

docker run --rm -it --gpus all -v $(pwd)/data:/data \
  --entrypoint bash ghcr.io/jialiangsun873-pixel/gromacs-mcp:2024-gpu

# 容器内
gmx --version | grep GPU
nvidia-smi
python -c "import MDAnalysis; print('OK')"

---
数据挂载

所有输入/输出文件通过 -v 挂载进出容器：

-v /your/data:/data

容器内工作目录为 /data，PDB、GRO、XTC 等文件均在此读写。

---
环境信息

┌─────────────────────────────┬────────────────────────┬───────────────────────────────────┐
│            组件             │         CPU 版         │              GPU 版               │
├─────────────────────────────┼────────────────────────┼───────────────────────────────────┤
│ 基础镜像                    │ continuumio/miniconda3 │ nvidia/cuda:12.5.0-runtime        │
├─────────────────────────────┼────────────────────────┼───────────────────────────────────┤
│ GROMACS                     │ 2024 (conda-forge)     │ 2024.5 (源码编译, -DGMX_GPU=CUD
├─────────────────────────────┼────────────────────────┼───────────────────────────────────┤
│ CUDA                        │ —                      │ 12.5, SM 89 (RTX 4070 优化)       │
├─────────────────────────────┼────────────────────────┼────────────────────────────────
│ Python                      │ 3.12                   │ 3.12                              │
├─────────────────────────────┼────────────────────────┼───────────────────────────────────┤
│ MDAnalysis                  │ ✅                     │ ✅                                │
├─────────────────────────────┼────────────────────────┼────────────────────────────────
│ FastMCP                     │ ✅                     │ ✅                                │
├─────────────────────────────┼────────────────────────┼───────────────────────────────────┤
│ NumPy / Pandas / Matplotlib │ ✅                     │ ✅                                │
└─────────────────────────────┴────────────────────────┴───────────────────────────────────┘

---
与 Enzyme Agency 集成

Enzyme Agency 的计算专家 Agent 自动加载 GROMACS 工具：

Agent 调用 gmx_production_md
  → mcp_bridge 检测 GPU 镜像可用
    ├── 存在 → docker run --gpus all gromacs-mcp:2024-gpu   ✅ GPU 加速
    └── 不存在 → docker run gromacs-mcp:2024                ✅ CPU fallback

Agent 无需感知底层是 CPU 还是 GPU，工具层自动选择最优执行路径。

集群部署

services:
  gromacs:
    image: ghcr.io/jialiangsun873-pixel/gromacs-mcp:2024
    stdin_open: true
    volumes:
      - /shared/data:/data

  gromacs-gpu:
    image: ghcr.io/jialiangsun873-pixel/gromacs-mcp:2024-gpu
    stdin_open: true
    volumes:
      - /shared/data:/data
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities:
                - gpu

---
版本历史

┌───────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│       版本        │                                                 Release                    │
├───────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ v2024 (CPU + GPU) │ GROMACS Release (https://github.com/jialiangsun873-pixel/enzyme-engineering-agent/releases/tag/GROMACS) │
└───────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────┘

更多镜像: GitHub Packages (https://github.com/jialiangsun873-pixel?tab=packages)
