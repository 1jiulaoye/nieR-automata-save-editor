# NieR:Automata Save Editor 🎮

> **《尼尔：机械纪元》存档修改器** — 图形界面修改金币、道具、芯片，即改即用

[![GitHub release](https://img.shields.io/github/v/release/1jiulaoye/nieR-automata-save-editor)](https://github.com/1jiulaoye/nieR-automata-save-editor/releases)
[![下载量](https://img.shields.io/github/downloads/1jiulaoye/nieR-automata-save-editor/total)](https://github.com/1jiulaoye/nieR-automata-save-editor/releases)
[![平台](https://img.shields.io/badge/platform-Windows-blue)](https://github.com/1jiulaoye/nieR-automata-save-editor/releases)
[![许可证](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 📌 项目介绍

**NieR:Automata Save Editor** 是一款为《尼尔：机械纪元》（NieR:Automata）玩家量身打造的**存档修改工具**。

无需折腾复杂的 Cheat Engine 或命令行脚本，通过漂亮的图形界面即可轻松修改存档中的 **金币（G）**、**消耗品道具**、**素材**、**武器** 以及 **Plug-in Chip（芯片）** 数据。保存后启动游戏，修改即刻生效。

> 🐱 由 [小柒的百宝箱](https://keaixiaoqi.cn) 制作维护，专为 PC 版（Steam / Microsoft Store）设计。

🌐 **在线展示页**：[1jiulaoye.github.io/nieR-automata-save-editor](https://1jiulaoye.github.io/nieR-automata-save-editor/)

---

## ✨ 功能一览

### 💰 金币修改
- 直接读取/修改存档中的金币数量（G）
- 支持输入任意数值，保存即生效
- 可配合 MAX 按钮一键改满

### 📦 道具编辑
- 查看当前存档中所有道具清单
- 支持添加/删除道具，一键增删
- 收录 **260 条**条目：221 个道具 + **39 把武器**（小型剑 / 大型剑 / 长枪 / 格斗，含 DLC）
- 道具/武器名称全中文显示，按分类筛选（材料、贵重品、关键道具、收藏品、外观、武器等）
- 武器升级等级不在此表内，工具只保证物品存在与名称正确

### 🧩 芯片编辑
- 查看/添加/删除/替换所有 Plug-in Chip
- 完整收录 **50 种芯片**（31 普通 × 9 等级 + 19 系统）及对应**效果说明**（如「自动拾取物品」「冲击波」「移动速度上升」等）
- 支持调整芯片等级
- 一键清空或填满芯片槽位

### 📁 多存档位支持
- 支持 `SlotData_0` / `SlotData_1` / `SlotData_2` 三个存档位切换
- 切换存档时自动提示保存，避免误操作
- 即改即用，无需退出游戏

---

## 📥 下载安装

### 最新版本：v1.3

| 文件 | 大小 | 下载 |
|------|------|------|
| `nier-save-editor-v1.3.zip` | ~20 MB | [⬇️ 点击下载](https://keaixiaoqi.cn/downloads/nier-save-editor-v1.3.zip) |
| GitHub Release | — | [⬇️ 从 GitHub 下载](https://github.com/1jiulaoye/nieR-automata-save-editor/releases) |

> **系统要求**：Windows 7 及以上（64位）
>
> **无需安装** — 下载 zip → 解压 → 运行 `nieR-save-editor.exe` 即可

### 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v1.4 | 2026-10 | 🛠️ 数据核对（补 107 个道具 + 39 把武器，修正 3 个错号）；写入改为两阶段事务（双文件全部落盘成功才替换，失败用备份回滚）、恢复先快照再原子替换、备份改用 opid + manifest（同秒不覆盖、只认同一次操作的成对文件）；修复切档“丢弃”仍写盘、小恢复药不显示、全 0 芯片误判、分类区间重叠、索引越界改到金币；界面加固：数量输入校验、满 255 提示、下拉框只读、武器强制数量 1、系统芯片等级锁定 |
| v1.3 | 2026-05 | 🎉 修复数据同步问题，金币/道具以 SlotData 为准；切换存档提示保存 |
| v1.2 | 2026-05 | 🧩 修复芯片数据解析（48字节对齐）；添加芯片效果展示；道具添加异常保护 |
| v1.1 | 2026-05 | 🐛 修复保存时文件膨胀问题；稳定性优化 |
| v1.0 | 2026-05 | 🎊 首次发布：支持金币/道具/芯片修改，多存档位 |

---

## 🚀 快速上手

### 第一步：找到你的存档

《尼尔：机械纪元》的存档文件位于：

```
%USERPROFILE%\Documents\My Games\NieR_Automata\
```

目录下有三个存档文件：
- `SlotData_0.dat` — 存档位 1
- `SlotData_1.dat` — 存档位 2
- `SlotData_2.dat` — 存档位 3

> ⚠️ **强烈建议**：修改前先**备份**存档文件！复制一份到安全位置。

### 第二步：打开存档

1. 运行 `nieR-save-editor.exe`
2. 点击 **「打开存档」** 按钮
3. 选择你的存档文件（如 `SlotData_0.dat`）

### 第三步：修改数据

#### 修改金币
- 切换到 **「金币」** 标签页
- 输入想要的金额（或点击「MAX」填满）
- ⚡ 即时预览当前金币数值

#### 修改道具
- 切换到 **「道具」** 标签页
- 点击 **「添加道具」** 从列表中选择
- 或选择已有道具点击 **「删除」**

#### 修改芯片
- 切换到 **「芯片」** 标签页
- 表格中显示所有已装备芯片及其效果
- 可添加/替换/删除芯片
- 支持调整芯片等级

### 第四步：保存生效

1. 点击 **「保存」** 按钮
2. 程序自动写入修改
3. 启动（或切换回）游戏，修改立即可见 ✅

---

## 🧠 常见问题 (FAQ)

### ❓ 修改后游戏里没变化？
- 确保保存的是 `SlotData_#.dat` 文件（不是 `GameData.dat`）
- 游戏可能缓存了数据，尝试**重新读取存档**（在游戏中存档一次再读档）

### ❓ 会不会封号？
- 《尼尔：机械纪元》是**单机游戏**，没有反作弊系统，修改存档不会被封号 ✅
- 但建议不要用于联机内容（如果有）

### ❓ 支持哪些游戏版本？
- Steam 版 ✅
- Microsoft Store / Game Pass 版 ✅
- 理论上所有 PC 版本均可

### ❓ 需要安装 Python 吗？
- **不需要**。下载的 exe 是打包好的独立程序，双击即可运行 🎉

### ❓ 道具列表不全怎么办？
- 当前收录 260 条（221 道具 + 39 武器），覆盖游戏内绝大部分条目。如发现缺失，欢迎提 [Issue](https://github.com/1jiulaoye/nieR-automata-save-editor/issues) 反馈，附上名称与用途即可

### ❓ 备份放在哪？会不会覆盖掉？
- 备份在 `My Games\NieR_Automata_backup`，文件名带每次操作的 `opid`（微秒时间戳 + 4 位随机），**同一秒连续备份也不会互相覆盖**
- 每次保存/备份会写 `manifest.json`，记录这次操作涉及哪几个文件、属于哪个存档位、sha256
- 恢复时只认同一次操作、且包含当前存档位的成对文件；旧版备份（没有 manifest）按同秒分组兜底，配不上就明确报错，不会跨槽混搭

### ❓ 存档会不会被写坏？
- 两个文件都先写临时文件并落盘，**全部成功后才替换**，任一失败就用保存前备份回滚
- 恢复备份前会先给当前存档做一次快照，失败可回滚
- 小于正常长度的文件会被拒绝载入，不会零填充后写回


---

## 🛠️ 技术细节

### 存档文件结构

```
SlotData_#.dat
├── 0x3056C  金币 (G)        — uint32 LE，4 字节
├── 0x30570  道具列表        — 定长数组，每条 12 字节，SlotData 内 512 条
│   ├── +0x00  道具 ID        — uint16 LE（0xFFFF 为空槽）
│   ├── +0x02  填充           — 4 字节
│   ├── +0x06  固定标记       — 07 00
│   ├── +0x08  数量           — uint8（最大 255）
│   └── +0x09  填充           — 3 字节
└── 0x324BC  芯片列表        — 定长数组，每条 48 字节（12 个 int32）
    ├── +0x00  chip_id_1 / chip_id_2 / type_id  — 3 × int32
    ├── +0x0C  等级           — int32
    ├── +0x10  占用格数        — int32
    ├── +0x14  坐标 x/y/z      — 3 × int32
    └── +0x20  填充           — 4 × int32（空槽为全 0xFF）
```

### 技术栈

| 组件 | 技术 |
|------|------|
| 编程语言 | Python 3.11 |
| GUI 框架 | Tkinter（系统原生，轻量快速） |
| 打包工具 | PyInstaller（单文件 exe） |
| 交叉编译 | Wine（Linux 环境生成 Windows 程序） |

### 项目结构

```
nier-save-editor/
├── nier_editor.py      # 🖥️ 主界面程序（GUI + 事件处理）
├── save_io.py          # 📄 存档读写模块（文件解析 + 原子写入 + 备份）
├── chip_data.py        # 🧩 芯片数据（31 普通 × 9 等级 + 19 系统芯片 + 效果说明）
├── item_data.py        # 📦 道具/武器数据（260 条中文名称 + 分类区间）
├── constants.py        # 🔧 常量定义（偏移量、记录大小、上限）
├── selftest.py         # ✅ 自检脚本（造存档 → 读 → 写 → 回读比对）
├── docs/index.html     # 🌐 展示页（GitHub Pages）
├── requirements.txt    # 📋 Python 依赖清单
├── LICENSE             # 📄 MIT
└── README.md           # 📖 项目说明（就是本文件）
```

---

## 🔧 自行编译

如果你希望从源码自行编译：

```bash
# 1. 克隆仓库
git clone https://github.com/1jiulaoye/nieR-automata-save-editor.git
cd nieR-automata-save-editor

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行（开发模式）
python nier_editor.py

# 4. 打包（生成 exe）
pip install pyinstaller
pyinstaller -F -w nier_editor.py --name nier-save-editor --add-data "chip_data.py;." --add-data "item_data.py;."
```

> 注：仓库里没有提交 `.spec` 文件，上面的命令即等价配置；如需自定义图标，自行加 `--icon icon.ico`。

---

## 📸 截图

![主界面预览](https://keaixiaoqi.cn/images/nier-editor-preview.png)

*（实际界面以最新版本为准）*

---

## 📄 许可说明

本项目基于 **MIT 许可证** 开源，仅供学习交流使用。

**请注意**：
- ⚠️ 修改存档可能影响游戏体验，建议先通关后再使用
- 🎮 请支持正版《尼尔：机械纪元》
- ❤️ 本工具完全免费，如遇收费下载请警惕

---

## 🤝 贡献

发现 Bug 或有建议？欢迎：
- 提交 [Issue](https://github.com/1jiulaoye/nieR-automata-save-editor/issues)
- 发起 [Pull Request](https://github.com/1jiulaoye/nieR-automata-save-editor/pulls)
- 在 [小柒的百宝箱](https://keaixiaoqi.cn) 留言反馈

---

## 🌐 相关链接

- 🏠 [小柒的百宝箱](https://keaixiaoqi.cn) — 更多游戏 Mod 和工具
- 🎮 [Nexus Mods: NieR:Automata](https://www.nexusmods.com/nierautomata) — 尼尔 Mod 社区
- 📖 [NieR:Automata Wiki](https://nierautomata.fandom.com/) — 游戏百科

---

> 🐱 **Made with ❤️ by 小柒**
>
> *「为了人类的荣耀——以及更轻松的游戏体验」*
