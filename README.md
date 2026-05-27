# Eye-Galvo Control

[![Python Verification](https://github.com/LiTongShuo-edu/eye-galvo-control/actions/workflows/python.yml/badge.svg)](https://github.com/LiTongShuo-edu/eye-galvo-control/actions/workflows/python.yml)

这是一个视线目标定位与振镜控制实验项目。系统通过 Intel RealSense 深度相机获取画面与深度信息，使用 MediaPipe Face Landmarker 定位双眼中心，将目标转换为相机坐标系中的三维位置，再通过 RIGOL DP832 输出振镜控制电压。项目已完成真实设备链路的功能验证，验证范围见 [硬件验证记录](./docs/hardware-validation.md)。

## 工作流程

```text
彩色图像 + 对齐深度
        |
MediaPipe 双眼中心定位
        |
像素/深度反投影为三维目标点
        |
已标定空间模型反求电压，或未标定角度映射
        |
PyVISA -> RIGOL DP832 -> 振镜输出
```

## 功能模块

| 模块 | 作用 |
| --- | --- |
| [`eye_galvo/geometry.py`](./eye_galvo/geometry.py) | 深度像素反投影、目标偏角计算以及基础电压映射 |
| [`eye_galvo/calibration.py`](./eye_galvo/calibration.py) | 近、中、远三个平面的九点亮斑采样，并导出校准模型 |
| [`eye_galvo/tracking.py`](./eye_galvo/tracking.py) | 实时视觉追踪、校准模型校验、目标位置到电压的反求与边界保护 |
| [`eye_galvo/instrument.py`](./eye_galvo/instrument.py) | DP832 的 VISA 通信、输出更新及退出时归中和关闭 |
| [`eye_galvo/cli.py`](./eye_galvo/cli.py) | `track`、`link`、`scan`、`calibrate` 命令入口 |

## 三平面标定

`calibrate` 使用 `4.0 V`、`5.0 V`、`6.0 V` 组成的 `3 x 3` 电压网格，依次在近距离平面、工作平面和远距离平面采集亮斑三维位置，共采集 27 个有效样本。对同一电压组合的三个空间点拟合一条光线，最终生成包含九条空间光线、残差和电压限制的 `galvo_calibration.json`。

联动追踪时：

- 存在有效的 `galvo_calibration.json` 时，根据目标三维位置在校准体积内反求输出电压。
- 未找到校准文件时，保留基于视角的受限电压映射，用于基础联动检查。
- 校准文件存在但损坏、版本不兼容或不满足边界约束时，拒绝开始联动输出。
- 目标超出允许校准体积时，保持当前输出而不继续无边界外推。

模型的数学构造和控制反求见 [眼-振镜空间标定模型](./docs/calibration-model.md)。

## 安装

推荐在 Python 3.12 虚拟环境中安装运行依赖：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

从 [MediaPipe Face Landmarker 官方模型地址](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task) 下载模型并保存为项目根目录下的 `face_landmarker.task`。模型文件不随源码发布。

## 使用

```powershell
# 仅视觉追踪，不连接仪器
.\.venv\Scripts\python.exe -m eye_galvo track --model .\face_landmarker.task

# 扫描可用 VISA 设备
.\.venv\Scripts\python.exe -m eye_galvo scan

# 采集三平面标定数据；默认输出 galvo_calibration.json
.\.venv\Scripts\python.exe -m eye_galvo calibrate --resource "YOUR_VISA_RESOURCE"

# 加载有效校准文件后联动追踪与 DP832
.\.venv\Scripts\python.exe -m eye_galvo link --resource "YOUR_VISA_RESOURCE" --model .\face_landmarker.task
```

设备资源地址也可通过 `DP832_RESOURCE` 环境变量传入。

## 测试与验证

无硬件测试覆盖空间计算、电压限幅、三平面数据完整性、射线模型校验、配置读写、异常配置拒绝以及仪器安全关闭序列：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m pytest
```

GitHub Actions 会在提交后运行同一组测试。自动测试用于复核可隔离的计算和控制边界；真实设备完成的功能链路验证单独记录在 [`docs/hardware-validation.md`](./docs/hardware-validation.md)，不将尚未量化测量的定位精度、响应时延或长期稳定性列为结论。

## 硬件与安全说明

- 实验设备范围为 Intel RealSense D435i 或兼容深度相机、RIGOL DP832、振镜组件及 VISA 后端。
- 联动流程退出时将振镜控制电压归中并关闭输出通道；首次连接前仍应人工确认电压范围、接线与光路安全。
- `face_landmarker.task`、`galvo_calibration.json`、真实仪器资源地址和实验画面均不作为源码提交。
