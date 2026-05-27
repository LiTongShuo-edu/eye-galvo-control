# Eye-Galvo Control

[![Python Verification](https://github.com/LiTongShuo-edu/eye-galvo-control/actions/workflows/python.yml/badge.svg)](https://github.com/LiTongShuo-edu/eye-galvo-control/actions/workflows/python.yml)

这是一个视觉定位与振镜控制实验项目。程序使用 Intel RealSense 深度相机和 MediaPipe Face Landmarker 获取双眼中心的三维位置与偏角，并通过 PyVISA 向 RIGOL DP832 输出振镜控制电压。公开版本重点展示 Python 数据处理、设备适配与可测试的安全控制逻辑。

## 快速阅读入口

| 希望核验的能力 | 查看位置 | 可重复验证内容 |
| --- | --- | --- |
| 三维坐标与角度换算 | [`eye_galvo/geometry.py`](./eye_galvo/geometry.py) | 无硬件单元测试 |
| 角度到电压、安全归位和关闭通道 | [`eye_galvo/instrument.py`](./eye_galvo/instrument.py) | 假设备命令序列测试 |
| RealSense + MediaPipe 视觉流程 | [`eye_galvo/tracking.py`](./eye_galvo/tracking.py) | 需要相机和模型文件 |
| DP832 联动与九点标定 | [`eye_galvo/cli.py`](./eye_galvo/cli.py)、[`eye_galvo/calibration.py`](./eye_galvo/calibration.py) | 需要实验硬件，验证记录见下文 |

## 对外运行入口

在 Python 3.12 虚拟环境中安装运行依赖：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

从 [MediaPipe Face Landmarker 官方模型存储地址](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task) 下载模型并保存为项目根目录下的 `face_landmarker.task`。模型文件不是本仓库源码的一部分，不随仓库发布。

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

## 无硬件自动验证

测试不连接相机或电源，仅覆盖能够稳定自动验证的纯计算逻辑与仪器命令安全序列：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m pytest
```

GitHub Actions 对同一组测试持续验证。自动测试通过不等同于视觉定位精度、振镜跟踪性能或完整实验效果已被测量。

## 硬件验证边界

- 实验设备范围：Intel RealSense D435i 或兼容深度相机、RIGOL DP832、振镜组件及 VISA 后端。
- 联动模式在退出时会将控制电压归中并关闭输出通道；首次连接前仍应人工确认限幅、接线与光路安全。
- 公开代码不含实际仪器资源地址、序列号、个人画面或实验日志。
- 本仓库当前提供实现和可重复的无硬件验证；带日期的现场联动/标定复核记录在完成复核后再加入 [`docs/hardware-validation.md`](./docs/hardware-validation.md)。
- 因此，未补入现场记录前，不据此宣称定位精度、响应速度或完整联动性能指标。

## AI 协作说明

该公开版本在 Codex 协助下完成模块拆分、配置脱敏、测试编排和文档整理。本人负责确认实验流程、公开范围、硬件安全边界和最终表述。本项目不将 AI 生成或未经现场验证的结论描述为实验性能成果。
