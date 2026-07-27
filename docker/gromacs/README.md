# GROMACS MCP Server — Docker 镜像

[![GROMACS](https://img.shields.io/badge/GROMACS-2024.5-blue)](https://www.gromacs.org/)
[![Python](https://img.shields.io/badge/Python-3.12-green)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-brightgreen)](https://www.docker.com/)

**把 GROMACS MD 管线暴露为 MCP 工具接口，Docker 一键部署，供 AI Agent 调用。**

```
PDB 文件 → pdb2gmx → solvate → add_ions → energy_minimize
    → NVT → NPT → production_md → RMSD/RMSF/HBonds 分析
```

---

## 内置工具 (MCP Tools)

| 工具 | 说明 |
|------|------|
| `pdb2gmx` | PDB → GROMACS 拓扑 (力场: amber99sb-ildn/charmm36/opls-aa) |
| `solvate` | 加水盒子 (cubic/dodecahedron) |
| `add_ions` | 加离子中和体系 (NaCl 生理盐浓度) |
| `energy_minimize` | 最陡下降能量最小化 |
| `run_nvt` | NVT 恒温恒体积平衡 |
| `run_npt` | NPT 恒温恒压平衡 |
| `production_md` | 生产 MD 模拟 (可指定时长) |
| `analyze_rmsd` | 轨迹 RMSD 分析 (MDAnalysis) |
| `analyze_rmsf` | 残基 RMSF 柔韧性分析 |
| `analyze_hbonds` | 氢键数量与 occupancy |

所有工具返回统一信封: `{"success": bool, "result": ..., "error": ...}`

---

## 快速开始

### 方式一：预构建镜像（推荐）

从 [GitHub Releases](../../releases) 下载 `gromacs-mcp-v2024.tar`，然后：

```bash
docker load -i gromacs-mcp-v2024.tar
docker run --rm -i -v "$(pwd)/data:/data" gromacs-mcp:latest
```

### 方式二：自行构建

```bash
# 克隆仓库
git clone https://github.com/YOUR_USERNAME/gromacs-mcp-docker.git
cd gromacs-mcp-docker

# 构建并运行
docker compose build
docker compose run --rm gromacs
```

> **注意**: 如果国内网络无法拉取 Docker Hub 基础镜像，请先在 Docker Desktop 设置中添加镜像加速器。

---

## 使用方法

### MCP 模式（AI Agent 调用）

```bash
docker run --rm -i \
  -v "/your/data/path:/data" \
  gromacs-mcp:latest
```

### 交互调试

```bash
docker run --rm -it --entrypoint bash \
  -v "/your/data/path:/data" \
  gromacs-mcp:latest
```

进入容器后可以手动执行 GROMACS 命令：
```bash
gmx pdb2gmx -f input.pdb -o protein.gro -p topol.top -ff amber99sb-ildn -water tip3p
```

---

## 数据挂载

把 PDB 文件放在本地目录（如 `./data`），挂载进容器的 `/data`：

```bash
# 目录结构
./data/
  ├── input.pdb          # 你放进去的 PDB
  ├── topol.top          # pdb2gmx 生成
  ├── protein.gro
  ├── em.tpr / em.gro    # 能量最小化
  ├── nvt.tpr / nvt.gro  # NVT 平衡
  ├── npt.tpr / npt.gro  # NPT 平衡
  └── md.xtc / md.tpr    # 生产轨迹
```

---

## 环境信息

| 组件 | 版本 |
|------|------|
| GROMACS | 2024.5 (conda-forge, AVX2_256) |
| Python | 3.12 |
| MDAnalysis | 2.10+ |
| NumPy | 2.x |
| FastMCP | 3.x |

---

## 与 Enzyme Agency 集成

本镜像作为 [Enzyme Agency](https://github.com/YOUR_USERNAME/enzyme-agency) 的 MD 模拟引擎，通过 MCP stdio 协议桥接。

Enzyme Agency 的计算专家 Agent 会自动检测并调用这些 GROMACS 工具进行：
- 酶-底物 MD 模拟
- 表面残基筛选
- 接触频率分析
- 突变位点建议
