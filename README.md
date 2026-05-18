# NieR:Automata Save Editor 🎮

> 尼尔：机械纪元 存档修改器 | 支持中文

一款带图形界面的 **《尼尔：机械纪元》存档修改工具**，可以自由修改游戏存档中的 **金币、道具、芯片** 数据。

由 [小柒](https://keaixiaoqi.cn) 制作维护 🐱

---

## ✨ 功能特点

- **💰 金币修改** — 直接修改游戏内金币（G）数量
- **📦 道具编辑** — 添加/删除游戏内的消耗品、素材、武器等
- **🧩 芯片编辑** — 添加/删除/替换各类 Plug-in Chip，支持查看效果
- **📁 多存档位支持** — 支持 SlotData_0~2 三个存档位切换
- **🔒 即改即用** — 修改后保存，启动游戏即可生效
- **🖥️ 图形界面** — 纯 GUI 操作，无需命令行
- **🌏 全中文界面** — 界面和道具名称均为中文

## 🖼️ 界面预览

![主界面](https://keaixiaoqi.cn/images/nier-editor-preview.png)

> *（实际界面以最新版本为准）*

## 📥 下载

| 版本 | 下载链接 | 说明 |
|------|---------|------|
| v1.3 | [nier-save-editor-v1.3.zip](https://keaixiaoqi.cn/downloads/nier-save-editor-v1.3.zip) | 最新稳定版，推荐下载 |

> ⚠️ **注意**：修改存档前建议**备份原文件**！游戏存档位置通常在：
> `%USERPROFILE%\Documents\My Games\NieR_Automata\SlotData_0.dat`

## 🚀 使用说明

1. 下载并解压 `nier-save-editor-v1.3.zip`
2. 运行 `nieR-save-editor.exe`
3. 点击 **「打开存档」** 按钮，选择你的 `SlotData_#.dat` 文件
4. 切换到 **金币 / 道具 / 芯片** 标签页进行修改
5. 点击 **「保存」** 按钮写入修改
6. 启动游戏，效果立竿见影 ✅

## 🛠️ 技术栈

- **语言**：Python 3.11
- **GUI 框架**：Tkinter（系统原生）
- **编译工具**：PyInstaller
- **交叉编译**：Wine（Linux → Windows exe）

## 📦 依赖

```
pip install -r requirements.txt
```

## 📁 项目结构

```
nier-save-editor/
├── nier_editor.py      # 主程序（GUI界面）
├── save_io.py          # 存档读写（数据解析）
├── chip_data.py        # 芯片数据（51种芯片+效果）
├── item_data.py        # 道具数据（全中文名称）
├── constants.py        # 常量定义
└── requirements.txt    # Python依赖
```

## 📄 开源许可

本项目仅供学习交流使用，**请支持正版游戏**。

---

> 🐱 由 [小柒的百宝箱](https://keaixiaoqi.cn) 出品
