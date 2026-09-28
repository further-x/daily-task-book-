# 每日任务本

一个离线运行的 Windows 桌面任务管理软件，使用 Python、CustomTkinter 和 SQLite 开发。

## 功能

- 创建任务，选择日常、工作、学习、兴趣或自定义分类。
- 按简单、普通、困难获得不同金币奖励，奖励数额可调整。
- 自定义商城奖励，记录每次兑换和累计兑换次数。
- 按实际完成时间记录金币日历，支持月度和历年统计。
- 已完成任务第二天自动从清单移除，完成记录和金币仍保留。
- 设置允许欠金币的额度，默认最低余额为 −100。
- 四种主题、自定义背景颜色、备份导入和导出。
- 带警告确认的恢复出厂设置。
- 导航、筛选和任务状态使用局部更新，减少切换闪烁。

## 直接使用

从本仓库的 Releases 下载 `每日任务本.exe`，双击运行。可执行版无需安装 Python。

## 从源码运行

建议使用 Python 3.12。进入项目文件夹，在终端执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest test_features -v
```

测试使用项目内独立的 `feature_test_data` 文件夹，不会操作用户的真实数据库。

## 打包为 Windows 程序

在 Windows 上执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed --collect-all customtkinter --name DailyTaskBook app.py
```

程序生成在 `dist/DailyTaskBook.exe`，可改名为 `每日任务本.exe`。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `app.py` | 窗口、页面和用户交互 |
| `task_store.py` | 数据库、任务、金币和统计逻辑 |
| `test_features.py` | 跨天清理、金币下限和数据重置测试 |
| `requirements.txt` | 运行源码所需依赖 |
| `requirements-dev.txt` | 打包依赖 |
| `.gitignore` | 排除数据库、缓存和打包文件 |
| `使用说明.md` | 软件使用说明 |

## 数据保存

用户数据存放于 `%APPDATA%\每日任务本\tasks.db`，离线保存在本机。

删除已完成任务仅从清单移除，金币及日历记录保留。撤销完成会扣回金币，并受欠金币额度限制。

恢复出厂设置会清空当前数据库中的任务、历史、商城、金币及兑换记录；操作前建议导出备份。导入备份前程序会自动备份原数据。
