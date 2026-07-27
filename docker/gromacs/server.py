"""
GROMACS MCP Server
==================
把 GROMACS 命令行工具暴露为 MCP 接口, Docker 部署。

提供的工具:
  pdb2gmx          — PDB → GROMACS 拓扑 (MD 第一步)
  solvate          — 加水盒子
  add_ions         — 加离子中和体系
  energy_minimize  — 能量最小化
  run_nvt          — NVT 平衡
  run_npt          — NPT 平衡
  production_md    — 生产 MD 模拟
  analyze_rmsd     — 轨迹 RMSD 分析
  analyze_rmsf     — 轨迹 RMSF 分析
  analyze_hbonds   — 氢键分析

所有工具返回统一信封: {"success": bool, "result": ..., "error": ...}
"""

import os
import subprocess
import json
from pathlib import Path
from fastmcp import FastMCP

mcp = FastMCP("gromacs")


# ── 辅助函数 ─────────────────────────────────────────────

def _run(cmd: list, cwd: str = "/data", timeout: int = 3600) -> dict:
    """在容器内执行命令, 返回 (returncode, stdout, stderr)"""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=cwd, timeout=timeout
        )
        return {"ok": r.returncode == 0, "stdout": r.stdout, "stderr": r.stderr}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"命令超时 ({timeout}s)"}
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": f"命令未找到: {cmd[0]}"}


def _ok(result: dict) -> dict:
    return {"success": True, "result": result, "error": None}


def _err(msg: str) -> dict:
    return {"success": False, "result": None, "error": msg}


# ── MD 准备工具 ──────────────────────────────────────────

@mcp.tool
def pdb2gmx(
    input_pdb: str,
    output_dir: str = "/data",
    force_field: str = "amber99sb-ildn",
    water_model: str = "tip3p",
) -> dict:
    """PDB → GROMACS 拓扑文件。MD 模拟的第一步。

    什么时候调用: 用户提供 PDB 文件, 需要开始 MD 模拟。

    Args:
        input_pdb: 蛋白质 PDB 文件路径
        output_dir: 输出目录, 默认 /data
        force_field: 力场, amber99sb-ildn / charmm36 / opls-aa
        water_model: 水模型, tip3p / spc / tip4p
    """
    stem = Path(input_pdb).stem
    os.makedirs(output_dir, exist_ok=True)

    r = _run([
        "gmx", "pdb2gmx",
        "-f", input_pdb,
        "-o", f"{output_dir}/{stem}.gro",
        "-p", f"{output_dir}/{stem}.top",
        "-ff", force_field,
        "-water", water_model,
        "-ignh",
    ], cwd=output_dir)

    if not r["ok"]:
        return _err(r["stderr"][-500:])

    return _ok({
        "gro_file": f"{output_dir}/{stem}.gro",
        "top_file": f"{output_dir}/{stem}.top",
        "next_step": "现在调用 solvate 加水盒子"
    })


@mcp.tool
def solvate(
    input_gro: str,
    topology: str,
    output_dir: str = "/data",
    box_margin: float = 1.0,
    box_shape: str = "cubic",
) -> dict:
    """给体系加水盒子。

    调用前提: 已经用 pdb2gmx 生成了 .gro 和 .top

    Args:
        input_gro: pdb2gmx 生成的 .gro 文件
        topology: pdb2gmx 生成的 .top 文件
        output_dir: 输出目录
        box_margin: 盒子到蛋白的最小距离 (nm)
        box_shape: cubic / dodecahedron
    """
    os.makedirs(output_dir, exist_ok=True)

    # editconf — 定义盒子
    r1 = _run([
        "gmx", "editconf",
        "-f", input_gro,
        "-o", f"{output_dir}/box.gro",
        "-c", "-d", str(box_margin), "-bt", box_shape,
    ], cwd=output_dir)
    if not r1["ok"]:
        return _err(f"editconf 失败: {r1['stderr'][-300:]}")

    # solvate — 加水
    r2 = _run([
        "gmx", "solvate",
        "-cp", f"{output_dir}/box.gro",
        "-cs", "spc216.gro",
        "-o", f"{output_dir}/solvated.gro",
        "-p", topology,
    ], cwd=output_dir)
    if not r2["ok"]:
        return _err(f"solvate 失败: {r2['stderr'][-300:]}")

    return _ok({
        "solvated_gro": f"{output_dir}/solvated.gro",
        "next_step": "现在调用 add_ions 加离子中和体系"
    })


@mcp.tool
def add_ions(
    input_gro: str,
    topology: str,
    output_dir: str = "/data",
    concentration: float = 0.150,
    pos_ion: str = "NA",
    neg_ion: str = "CL",
) -> dict:
    """加离子中和体系电荷。

    调用前提: 已经用 solvate 加过水盒子

    Args:
        input_gro: solvate 生成的 .gro 文件
        topology: 拓扑文件
        output_dir: 输出目录
        concentration: NaCl 浓度 (M), 默认 0.150 (生理盐浓度)
        pos_ion: 阳离子类型
        neg_ion: 阴离子类型
    """
    os.makedirs(output_dir, exist_ok=True)

    # 生成最小 ions.mdp
    mdp = f"{output_dir}/ions.mdp"
    if not os.path.exists(mdp):
        with open(mdp, "w") as f:
            f.write("integrator = steep\nnsteps = 0\n")

    r1 = _run([
        "gmx", "grompp",
        "-f", mdp,
        "-c", input_gro,
        "-p", topology,
        "-o", f"{output_dir}/ions.tpr",
    ], cwd=output_dir)
    if not r1["ok"]:
        return _err(f"grompp 失败: {r1['stderr'][-300:]}")

    r2 = _run([
        "gmx", "genion",
        "-s", f"{output_dir}/ions.tpr",
        "-o", f"{output_dir}/neutral.gro",
        "-p", topology,
        "-pname", pos_ion,
        "-nname", neg_ion,
        "-conc", str(concentration),
        "-neutral",
    ], cwd=output_dir)
    if not r2["ok"]:
        return _err(f"genion 失败: {r2['stderr'][-300:]}")

    return _ok({
        "neutral_gro": f"{output_dir}/neutral.gro",
        "ion_conc_M": concentration,
        "next_step": "现在调用 energy_minimize 做能量最小化"
    })


# ── MD 运行工具 ──────────────────────────────────────────

@mcp.tool
def energy_minimize(
    input_gro: str,
    topology: str,
    output_dir: str = "/data",
    nsteps: int = 50000,
) -> dict:
    """能量最小化 (steepest descent)。

    Args:
        input_gro: 起始结构文件
        topology: 拓扑文件
        output_dir: 输出目录
        nsteps: 最大步数
    """
    os.makedirs(output_dir, exist_ok=True)

    with open(f"{output_dir}/em.mdp", "w") as f:
        f.write(f"""integrator  = steep
nsteps      = {nsteps}
emtol       = 1000.0
emstep      = 0.01
nstxout     = 100
nstlog      = 100
nstenergy   = 100
cutoff-scheme = Verlet
nstlist     = 20
rlist       = 1.0
coulombtype = PME
rcoulomb    = 1.0
vdwtype     = Cut-off
rvdw        = 1.0
pbc         = xyz
""")

    r1 = _run([
        "gmx", "grompp",
        "-f", f"{output_dir}/em.mdp",
        "-c", input_gro,
        "-p", topology,
        "-o", f"{output_dir}/em.tpr",
    ], cwd=output_dir, timeout=60)
    if not r1["ok"]:
        return _err(f"grompp EM 失败: {r1['stderr'][-300:]}")

    r2 = _run([
        "gmx", "mdrun", "-v", "-deffnm", f"{output_dir}/em",
    ], cwd=output_dir)
    if not r2["ok"]:
        return _err(f"EM 失败: {r2['stderr'][-300:]}")

    return _ok({
        "em_gro": f"{output_dir}/em.gro",
        "next_step": "能量最小化完成, 现在调用 run_nvt 做 NVT 平衡"
    })


@mcp.tool
def run_nvt(
    input_gro: str,
    topology: str,
    output_dir: str = "/data",
    temperature: float = 310,
    nsteps: int = 100000,
) -> dict:
    """NVT 系综平衡 (恒温, 恒体积)。

    Args:
        input_gro: 起始结构 (通常为 em.gro)
        topology: 拓扑文件
        output_dir: 输出目录
        temperature: 温度 (K), 默认 310 (37°C)
        nsteps: 步数 (2fs 步长, 100000 = 200ps)
    """
    os.makedirs(output_dir, exist_ok=True)

    with open(f"{output_dir}/nvt.mdp", "w") as f:
        f.write(f"""integrator  = md
nsteps      = {nsteps}
dt          = 0.002
nstxout-compressed = 5000
nstenergy   = 5000
nstlog      = 5000
cutoff-scheme = Verlet
nstlist     = 20
rlist       = 1.0
coulombtype = PME
rcoulomb    = 1.0
vdwtype     = Cut-off
rvdw        = 1.0
tcoupl      = V-rescale
tc-grps     = System
tau-t       = 0.1
ref-t       = {temperature}
pcoupl      = no
pbc         = xyz
constraints = h-bonds
constraint-algorithm = LINCS
""")

    r1 = _run([
        "gmx", "grompp",
        "-f", f"{output_dir}/nvt.mdp",
        "-c", input_gro,
        "-p", topology,
        "-o", f"{output_dir}/nvt.tpr",
    ], cwd=output_dir, timeout=60)
    if not r1["ok"]:
        return _err(f"grompp NVT 失败: {r1['stderr'][-300:]}")

    r2 = _run([
        "gmx", "mdrun", "-v", "-deffnm", f"{output_dir}/nvt",
    ], cwd=output_dir)
    if not r2["ok"]:
        return _err(f"NVT 失败: {r2['stderr'][-300:]}")

    return _ok({
        "nvt_gro": f"{output_dir}/nvt.gro",
        "next_step": "NVT 完成, 现在调用 run_npt 做 NPT 平衡"
    })


@mcp.tool
def run_npt(
    input_gro: str,
    topology: str,
    output_dir: str = "/data",
    temperature: float = 310,
    pressure: float = 1.0,
    nsteps: int = 100000,
) -> dict:
    """NPT 系综平衡 (恒温, 恒压)。

    Args:
        input_gro: 起始结构 (通常为 nvt.gro)
        topology: 拓扑文件
        output_dir: 输出目录
        temperature: 温度 (K)
        pressure: 压力 (bar)
        nsteps: 步数
    """
    os.makedirs(output_dir, exist_ok=True)

    with open(f"{output_dir}/npt.mdp", "w") as f:
        f.write(f"""integrator  = md
nsteps      = {nsteps}
dt          = 0.002
nstxout-compressed = 5000
nstenergy   = 5000
nstlog      = 5000
cutoff-scheme = Verlet
nstlist     = 20
rlist       = 1.0
coulombtype = PME
rcoulomb    = 1.0
vdwtype     = Cut-off
rvdw        = 1.0
tcoupl      = V-rescale
tc-grps     = System
tau-t       = 0.1
ref-t       = {temperature}
pcoupl      = Parrinello-Rahman
pcoupltype  = isotropic
tau-p       = 2.0
ref-p       = {pressure}
compressibility = 4.5e-5
pbc         = xyz
constraints = h-bonds
constraint-algorithm = LINCS
""")

    r1 = _run([
        "gmx", "grompp",
        "-f", f"{output_dir}/npt.mdp",
        "-c", input_gro,
        "-p", topology,
        "-o", f"{output_dir}/npt.tpr",
    ], cwd=output_dir, timeout=60)
    if not r1["ok"]:
        return _err(f"grompp NPT 失败: {r1['stderr'][-300:]}")

    r2 = _run([
        "gmx", "mdrun", "-v", "-deffnm", f"{output_dir}/npt",
    ], cwd=output_dir)
    if not r2["ok"]:
        return _err(f"NPT 失败: {r2['stderr'][-300:]}")

    return _ok({
        "npt_gro": f"{output_dir}/npt.gro",
        "next_step": "NPT 完成, 体系已平衡。调用 production_md 跑生产模拟"
    })


@mcp.tool
def production_md(
    input_gro: str,
    topology: str,
    output_dir: str = "/data",
    duration_ns: float = 100.0,
    temperature: float = 310,
    pressure: float = 1.0,
) -> dict:
    """生产 MD 模拟。最耗时的一步。

    Args:
        input_gro: 平衡后的结构文件
        topology: 拓扑文件
        output_dir: 输出目录
        duration_ns: 模拟时长 (ns)
        temperature: 温度 (K)
        pressure: 压力 (bar)
    """
    os.makedirs(output_dir, exist_ok=True)
    nsteps = int(duration_ns * 500000)  # ns → 步数 (2fs 步长)

    with open(f"{output_dir}/md.mdp", "w") as f:
        f.write(f"""integrator  = md
nsteps      = {nsteps}
dt          = 0.002
nstxout-compressed = 5000
nstenergy   = 5000
nstlog      = 5000
cutoff-scheme = Verlet
nstlist     = 20
rlist       = 1.0
coulombtype = PME
rcoulomb    = 1.0
vdwtype     = Cut-off
rvdw        = 1.0
tcoupl      = V-rescale
tc-grps     = System
tau-t       = 0.1
ref-t       = {temperature}
pcoupl      = Parrinello-Rahman
pcoupltype  = isotropic
tau-p       = 2.0
ref-p       = {pressure}
compressibility = 4.5e-5
pbc         = xyz
constraints = h-bonds
constraint-algorithm = LINCS
""")

    r1 = _run([
        "gmx", "grompp",
        "-f", f"{output_dir}/md.mdp",
        "-c", input_gro,
        "-p", topology,
        "-o", f"{output_dir}/md.tpr",
    ], cwd=output_dir, timeout=60)
    if not r1["ok"]:
        return _err(f"grompp MD 失败: {r1['stderr'][-300:]}")

    r2 = _run([
        "gmx", "mdrun", "-v", "-deffnm", f"{output_dir}/md",
    ], cwd=output_dir, timeout=int(duration_ns * 3600))

    if not r2["ok"]:
        return _err(f"MD 失败: {r2['stderr'][-300:]}")

    return _ok({
        "trajectory_xtc": f"{output_dir}/md.xtc",
        "topology_tpr": f"{output_dir}/md.tpr",
        "log_file": f"{output_dir}/md.log",
        "duration_ns": duration_ns,
        "next_step": "MD 完成! 用 analyze_rmsd / analyze_rmsf 分析轨迹"
    })


# ── 分析工具 ─────────────────────────────────────────────

@mcp.tool
def analyze_rmsd(
    tpr: str,
    xtc: str,
    selection: str = "backbone",
    reference_frame: int = 0,
) -> dict:
    """计算轨迹 RMSD, 判断模拟是否达到平衡。

    Args:
        tpr: TPR 文件路径
        xtc: XTC 轨迹文件路径
        selection: 原子选择, backbone / c-alpha / protein
        reference_frame: 参考帧编号
    """
    try:
        import MDAnalysis as mda
        from MDAnalysis.analysis.rms import RMSD
        import numpy as np

        u = mda.Universe(tpr, xtc)
        atoms = u.select_atoms(selection)
        if len(atoms) == 0:
            atoms = u.select_atoms("not name H*")

        R = RMSD(atoms, atoms, ref_frame=reference_frame).run(
            start=0, stop=len(u.trajectory), step=1, verbose=False
        )

        rmsd_vals = R.results.rmsd[:, 2]
        times_ns = R.results.rmsd[:, 1] / 1000

        return _ok({
            "n_frames": len(u.trajectory),
            "mean_rmsd_nm": round(float(rmsd_vals.mean()), 4),
            "max_rmsd_nm": round(float(rmsd_vals.max()), 4),
            "final_rmsd_nm": round(float(rmsd_vals[-1]), 4),
            "rmsd_drift_nm": round(float(rmsd_vals[-1] - rmsd_vals[0]), 4),
            "stable": bool(rmsd_vals[-20:].std() < 0.05),
        })
    except Exception as e:
        return _err(str(e))


@mcp.tool
def analyze_rmsf(
    tpr: str,
    xtc: str,
    selection: str = "name CA",
) -> dict:
    """计算每个残基的 RMSF, 找出柔性区域。

    Args:
        tpr: TPR 文件路径
        xtc: XTC 轨迹文件路径
        selection: 原子选择, 默认 C-alpha
    """
    try:
        import MDAnalysis as mda
        from MDAnalysis.analysis.rms import RMSF
        import numpy as np

        u = mda.Universe(tpr, xtc)
        atoms = u.select_atoms(selection)
        if len(atoms) == 0:
            atoms = u.select_atoms("backbone")

        R = RMSF(atoms).run(verbose=False)
        residues = []
        for i in range(len(atoms)):
            residues.append({
                "resid": int(atoms.resids[i]),
                "resname": atoms.resnames[i],
                "rmsf_nm": round(float(R.results.rmsf[i]), 4),
            })

        top5 = sorted(residues, key=lambda r: r["rmsf_nm"], reverse=True)[:5]

        return _ok({
            "n_residues": len(residues),
            "top5_flexible": top5,
            "mean_rmsf_nm": round(float(np.mean([r["rmsf_nm"] for r in residues])), 4),
        })
    except Exception as e:
        return _err(str(e))


@mcp.tool
def analyze_hbonds(
    tpr: str,
    xtc: str,
    donors_sel: str = "protein",
    acceptors_sel: str = "protein",
) -> dict:
    """分析氢键数量和 occupancy。

    Args:
        tpr: TPR 文件路径
        xtc: XTC 轨迹文件路径
        donors_sel: 供体选择
        acceptors_sel: 受体选择
    """
    try:
        import MDAnalysis as mda
        from MDAnalysis.analysis.hydrogenbonds import HydrogenBondAnalysis
        import numpy as np

        u = mda.Universe(tpr, xtc)
        n_frames = len(u.trajectory)

        hba = HydrogenBondAnalysis(u, donors_sel=donors_sel, acceptors_sel=acceptors_sel)
        results = hba.run(verbose=False)

        counts = np.zeros(n_frames, dtype=int)
        for frame_idx in results.results.hbonds[:, 2].astype(int):
            frame_idx = min(frame_idx, n_frames - 1)
            counts[frame_idx] += 1

        return _ok({
            "n_frames": n_frames,
            "mean_hbonds": round(float(counts.mean()), 1),
            "max_hbonds": int(counts.max()),
            "stable_bonds": bool(counts[-50:].std() < 2.0),
        })
    except Exception as e:
        return _err(str(e))


if __name__ == "__main__":
    mcp.run()
