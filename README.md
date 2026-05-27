# Eye-Galvo Control

[![Python Verification](https://github.com/LiTongShuo-edu/eye-galvo-control/actions/workflows/python.yml/badge.svg)](https://github.com/LiTongShuo-edu/eye-galvo-control/actions/workflows/python.yml)

这是一个视觉定位与振镜控制实验项目。程序使用 Intel RealSense 深度相机和 MediaPipe Face Landmarker 获取双眼中心的三维位置与偏角，并通过 PyVISA 向 RIGOL DP832 输出振镜控制电压。项目将计算逻辑、仪器通信和运行流程拆分开，以便在没有实验硬件时测试核心控制行为。

## 功能概览

| 模块 | 查看位置 | 作用 |
| --- | --- | --- |
| 空间计算 | [`eye_galvo/geometry.py`](./eye_galvo/geometry.py) | 根据像素位置、深度和相机内参计算三维位置与偏角，并映射输出电压 |
| 仪器控制 | [`eye_galvo/instrument.py`](./eye_galvo/instrument.py) | 封装 VISA 通信、通道启用、电压更新以及退出时的安全关闭 |
| 视觉追踪 | [`eye_galvo/tracking.py`](./eye_galvo/tracking.py) | 组合 RealSense 深度流与 MediaPipe 人脸关键点，提供实时追踪流程 |
| 标定与命令入口 | [`eye_galvo/calibration.py`](./eye_galvo/calibration.py)、[`eye_galvo/cli.py`](./eye_galvo/cli.py) | 提供四种运行命令与九点标定数据采集 |

## 安装

在 Python 3.12 虚拟环境中安装运行依赖：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

从 [MediaPipe Face Landmarker 官方模型存储地址](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task) 下载模型并保存为项目根目录下的 `face_landmarker.task`。模型文件不是本仓库源码的一部分，不随仓库发布。

## 命令行使用

项目提供四种运行模式：

```powershell
# 仅视觉追踪，不连接仪器
.\.venv\Scripts\python.exe -m eye_galvo track --model .\face_landmarker.task

# 扫描可用 VISA 设备
.\.venv\Scripts\python.exe -m eye_galvo scan

# 视觉与振镜联动；设备地址通过参数或 DP832_RESOURCE 环境变量传入
.\.venv\Scripts\python.exe -m eye_galvo link --resource "YOUR_VISA_RESOURCE" --model .\face_landmarker.task

# 执行九点亮斑标定并导出标定参数
.\.venv\Scripts\python.exe -m eye_galvo calibrate --resource "YOUR_VISA_RESOURCE" --output calibration-output.json
```

## 测试

测试不连接相机或电源，覆盖空间计算、电压限幅以及设备退出时的安全命令序列：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m pytest
```

GitHub Actions 会在每次提交后运行同一组测试。自动测试验证的是可隔离的逻辑和控制序列，不代表视觉定位精度或完整硬件系统性能测量结果。

## 硬件与安全说明

- 实验设备范围：Intel RealSense D435i 或兼容深度相机、RIGOL DP832、振镜组件及 VISA 后端。
- 联动模式在退出时会将控制电压归中并关闭输出通道；首次连接前仍应人工确认限幅、接线与光路安全。
- 公开代码不含实际仪器资源地址、序列号、个人画面或实验日志。
- 带日期的现场联动/标定复核记录在完成复核后加入 [`docs/hardware-validation.md`](./docs/hardware-validation.md)。
- 未补入现场记录前，本仓库不提供定位精度、响应速度或完整联动性能指标。

## AI 协作说明

该公开版本在 Codex 协助下完成模块拆分、配置脱敏、测试编排和文档整理。本人负责确认实验流程、公开范围、硬件安全边界和最终表述。本项目不将 AI 生成或未经现场验证的结论描述为实验性能成果。
