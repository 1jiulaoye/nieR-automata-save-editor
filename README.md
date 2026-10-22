# 尼尔存档修改器

> **NieR:Automata Save Editor** — 图形界面直接改存档：金币、道具、武器、芯片，改完保存，回到游戏立刻生效。

[![最新版本](https://img.shields.io/github/v/release/1jiulaoye/nieR-automata-save-editor?label=release)](https://github.com/1jiulaoye/nieR-automata-save-editor/releases)
[![下载量](https://img.shields.io/github/downloads/1jiulaoye/nieR-automata-save-editor/total)](https://github.com/1jiulaoye/nieR-automata-save-editor/releases)
[![平台](https://img.shields.io/badge/platform-Windows%208.1%2B%20x64-blue)](https://github.com/1jiulaoye/nieR-automata-save-editor/releases)
[![许可证](https://img.shields.io/badge/license-MIT-green)](LICENSE)

🌐 在线展示页：<https://1jiulaoye.github.io/nieR-automata-save-editor/>

---

## 目录

- [为什么用它](#为什么用它)
- [功能](#功能)
- [下载与安装](#下载与安装)
- [快速上手](#快速上手)
- [各个页面怎么用](#各个页面怎么用)
- [它怎么保证不写坏存档](#它怎么保证不写坏存档)
- [常见问题](#常见问题)
- [存档文件结构](#存档文件结构)
- [从源码运行 / 自行编译](#从源码运行--自行编译)
- [数据来源与验证](#数据来源与验证)
- [版本历史](#版本历史)
- [反馈与贡献](#反馈与贡献)

---

## 为什么用它

《尼尔：机械纪元》的存档是定长二进制结构：金币在 `0x3056C`，背包是 256 条 12 字节记录，武器是另一张 39 条 20 字节的表，芯片又是 256 条 48 字节的记录。用 Cheat Engine 改要一条条试偏移，改错一个字节就可能读不出档。

这个工具把这些都做成了界面：

- 不用记偏移量，打开存档就能看到金币、道具、武器、芯片
- 中文名称表来自社区实测数据（221 个道具 + 39 把武器 + 50 种芯片）
- 写入是**两阶段事务**：两个文件都落盘成功才替换，失败自动回滚
- 每次改完自动备份，备份带 `manifest.json`（opid / 槽位 / sha256）；恢复只认同一次操作的成对文件，不会把 A 槽的 GameData 和 B 槽的 SlotData 拼在一起

单机游戏，没有反作弊，改存档不会被封号。但建议先自己通关一遍，别把体验一次改没了。

---

## 功能

### 💰 金币
- 读取当前存档位金币，改成任意数值
- 「填满最大」一键写成 `4,294,967,295`
- 保存时同时写入 `GameData.dat` 和当前 `SlotData_#.dat`，两边保持一致

### 📦 道具
- 背包 **256 格**，列出全部持有道具（中文名 / 数量 / ID）
- 添加、删除、改数量（1–255），按名称搜索，按分类筛选：恢复 / 状态治疗 / 战斗增幅 / 材料 / 贵重品 / 关键道具 / 收藏品 / 外观 …
- 尸体背包（阵亡掉落的另外 256 格）单独只读展示，不会和背包混在一起

### ⚔️ 武器
- 武器不在道具表里，是独立的 **39 条 × 20 字节**表
- 显示名称、等级（1–4）、是否已获得
- 支持改等级、添加、删除武器

### 🧩 芯片
- 芯片表 **256 格**，每格 48 字节；列出已装芯片的名称、等级、占用格数、效果说明
- 收录 50 种芯片：31 种普通芯片 × 9 个等级 + 19 种系统芯片（OS 芯片、HUD 系列、自动攻击 / 射击 / 闪避 / 骇入 / 换武器…）
- 支持添加、删除、替换芯片

### 💾 备份
- 保存前自动备份 `GameData.dat` 和当前 `SlotData_#.dat`
- 备份文件名带 opid（微秒时间戳 + 4 位随机），**同一秒连续备份不会互相覆盖**
- 状态栏「备份 ▾」可手动备份 / 从备份恢复；恢复前会先给当前存档做一次快照

---

## 下载与安装

### 最新版本：v1.4.0

| 文件 | 大小 | 下载 |
|------|------|------|
| `nier-save-editor-v1.4-win64-portable.zip`（**绿色版，推荐**：用官方签名的 pythonw 启动，绕开 Smart App Control） | ~22 MB | [⬇️ 点击下载](https://github.com/1jiulaoye/nieR-automata-save-editor/releases/download/v1.4.0/nier-save-editor-v1.4-win64-portable.zip) |
| `nier-save-editor-v1.4-win64.zip`（单文件） | ~20 MB | [⬇️ 点击下载](https://github.com/1jiulaoye/nieR-automata-save-editor/releases/download/v1.4.0/nier-save-editor-v1.4-win64.zip) |
| `nier-save-editor-v1.4-win64-onedir.zip`（目录版，被 Smart App Control 拦时试这个） | ~20 MB | [⬇️ 点击下载](https://github.com/1jiulaoye/nieR-automata-save-editor/releases/download/v1.4.0/nier-save-editor-v1.4-win64-onedir.zip) |
| 历史版本 | — | [Releases](https://github.com/1jiulaoye/nieR-automata-save-editor/releases) |

> **系统要求**：Windows 8.1 / 10 / 11（64 位）
>
> **无需安装**：下载 zip → 解压 → 双击 `nier-save-editor.exe`
>
> exe 用 Python 3.11 打包，所以不再支持 Windows 7。杀毒软件可能对 PyInstaller 单文件 exe 误报，加信任即可；需要目录版（非 onefile）可以提 Issue。

---

## 快速上手

### 1. 找到存档

```
C:\Users\<你的用户名>\Documents\My Games\NieR_Automata\
```

按 `Win + R` 粘贴下面这行可以直接打开：

```
%USERPROFILE%\Documents\My Games\NieR_Automata
```

目录里通常有：

```
GameData.dat      全局数据
SlotData_0.dat    存档位 1
SlotData_1.dat    存档位 2
SlotData_2.dat    存档位 3
SystemData.dat    系统数据（本工具不改）
```

> 开了 OneDrive 文档同步的话，路径在 `%USERPROFILE%\OneDrive\Documents\My Games\NieR_Automata`
>
> Game Pass / Microsoft Store 版如果不在这个目录，在 C 盘搜 `SlotData_0.dat` 就能定位

### 2. 打开

启动程序后会自动找上面的路径；找不到就点左上角「打开存档文件夹」手动选 `NieR_Automata` 目录。

### 3. 选存档位

右上角 `1 / 2 / 3` 对应 `SlotData_0/1/2.dat`。切存档位时如果有未保存修改，会问你是否丢弃；选「是」会从磁盘重新载入，旧槽的修改不会泄漏到新槽。

### 4. 改，然后保存

改完点右上角「保存修改」。程序会：先备份 → 两个文件都写临时文件并落盘 → 全部成功才替换 → 提示已写入哪几个文件。

### 5. 回到游戏

启动游戏或重新读档，修改即刻生效。如果没变化，先在游戏里存一次档再读回来（游戏会缓存数据）。

---

## 各个页面怎么用

| 页面 | 能做什么 | 操作行 |
|---|---|---|
| 金币 | 看当前金币，输入新数值 | 设为 / 填满最大 |
| 道具 | 背包列表，搜索 + 分类筛选 | 数量输入 + 增加 / 减少 / 设为；右侧「添加」从只读下拉框选道具 |
| 武器 | 39 条武器表，显示等级与是否获得 | 等级 1–4 + 保存等级；下拉选武器 + 添加 / 删除 |
| 芯片 | 已装芯片列表（名称 / 等级 / 格数 / 效果），右上显示 `已装 x / 256` | 下拉选芯片 + 等级 + 添加 / 删除 |

小细节：

- 道具数量上限 255，输入 `-10` / `0` / `300` / `abc` 都会被拒绝并提示，不会写盘
- 武器不可堆叠，数量固定 1，重复添加不会累加
- 选中系统芯片时等级框会置灰 —— 它们是固定等级
- 道具 / 芯片 / 武器下拉框都是只读的，避免手打出无效 ID 写进存档
- 越界索引（`-1`、超过 256）会直接抛错，不会写到金币或别的区域

---

## 它怎么保证不写坏存档

改存档最怕两件事：写一半断电、两个文件对不上。这个工具的做法：

1. **拒绝无效文件**：小于该类型最小长度（`GameData` 397,683 字节 / `SlotData` 230,588 字节）的文件直接拒绝载入，绝不零填充后写回。
2. **长度不变**：永远按原文件长度写回，不会把 200KB 的存档悄悄写成 230KB。
3. **两阶段写入**：先把数据写到同目录 `.tmp` 并 `fsync`，两个文件都成功后才 `os.replace` 替换；任一步失败就清掉临时文件、用保存前备份回滚，内存里的「已修改」标记也恢复，可以直接重试。
4. **备份可追溯**：`My Games\NieR_Automata_backup\` 里每次操作一组文件，文件名带 opid，`manifest.json` 记录这次操作涉及哪些文件、属于哪个存档位、sha256。恢复时只认同一 opid 且包含当前槽位的成对文件；旧格式备份按同秒分组兜底，配不上就明确报错，不会跨槽混搭。
5. **恢复也原子**：恢复前先给当前存档做一次成对快照，再临时文件 + 替换 + 回读校验，失败用快照回滚。
6. **自检脚本**：仓库里 `selftest.py` 有 198 项自动检查（读写、边界、备份、武器表、芯片判空、索引越界…），一条命令跑完。

```
$ python3 selftest.py
结果：198 通过 / 0 失败
```

---

## 常见问题

### ❓ 改完进游戏没变化？
- 确认改的是当前选中的存档位（`SlotData_#.dat`）
- 游戏内数据有缓存：先在游戏里存一次档，再读回来
- 不要同时开两个修改器实例写同一个文件

### ❓ 会被封号吗？
《尼尔：机械纪元》是单机游戏，没有反作弊系统，改存档不会封号。但仍建议先自己通关一遍再用。

### ❓ 双击没反应 / 被「智能应用控制（Smart App Control）」拦了？
Win11 的 Smart App Control 只放行有数字签名的程序，PyInstaller 打包的 exe 一律拦，而且**没有白名单**，弹窗里也没有“仍要运行”。三条路：

1. **用绿色版**（推荐，不用动 SAC）：下载 `-portable` 那个包，双击里面的「启动.bat」。它用 Python 官方的 `pythonw.exe`（有微软信任的签名）来跑程序，SAC 会当成 Python 运行时放行
2. **换目录版**：下载 `-onedir` 那个包，解压后双击 `nier-save-editor.exe`。目录版不会先把自己解压到 `%TEMP%` 再执行，触发条件少一层（但不保证一定过）
3. **关掉 SAC**：设置 → 隐私和安全性 → Windows 安全中心 → 应用和浏览器控制 → 智能应用控制 → 关闭
   ⚠️ 注意：SAC 关掉后只能重装系统才能再打开，自己权衡
4. **从源码跑**：装 Python 3.11+，`pip install "ttkbootstrap>=1.10,<3"`，然后 `python nier_editor.py`

**为什么这些办法有效 / 无效**

微软官方对 SAC 的判定顺序是：先问云端信誉服务，能给出明确结论就按结论执行；判断不了才看签名 —— 有有效签名就放行，没签名或签名无效就拦（[MS FAQ](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions)）。所以：

- **自签名没用**：自签证书的根是你自己，不在微软信任链里；手动装进「受信任的根证书颁发机构」也只影响本机的 UAC/属性显示，SAC 依然拦
- **绿色版有效**：跑的是 Python 官方的 `pythonw.exe`，它在微软信任链里，签名有效 → 直接放行。这也是社区里最常用的做法（“用签名解释器跑未签名代码”），参考 [dev.to 这篇](https://dev.to/milkyway008/windows-smart-app-control-is-blocking-your-python-clis-os-error-4551-what-to-do-4bkj) 和 [note.com 这篇](https://note.com/liuk_net/n/n5b11e4018dfc?hl=en)
- **没有白名单**：微软明确写了 “There is currently no way to bypass Smart App Control protection for individual apps”，别去找“加入信任”的开关，没有

**长期方案（按成本排）**

| 方案 | 成本 | 说明 |
|---|---|---|
| 绿色版 / 源码运行 | 0 | 现在就能用，缺点是有个 `python` 目录、体积 20MB+ |
| [SignPath Foundation](https://signpath.org/) 免费 OSS 签名 | 0 | 面向开源项目：OSI 许可、无专有组件、持续维护、已发布、有文档。证书签发给 SignPath Foundation（他们是发布者），构建要走他们的 CI |
| [Azure Artifact Signing](https://azure.microsoft.com/en-us/pricing/details/artifact-signing/)（原 Trusted Signing） | 约 $9.99/月起 | 公信证书目前只对部分国家/地区的组织开放（美国、加拿大、欧盟、英国、澳、新西兰、日本、韩国、新加坡、瑞士），中国大陆不在名单里 |
| 上架 Microsoft Store | 一次性 $19 | Store 分发的应用由商店签名，不受 SAC 拦；但要过审核，存档修改器这类工具能不能过不好说 |
| 传统 OV / EV 代码签名证书 | 每年几百到几千 | 最直接，EV 还能立刻拿到 SmartScreen 信誉 |

**顺便更正一句**：以前流传“SAC 关掉后只能重装系统才能再开”。微软 2026 年的 FAQ 已经改成「近期 Windows 更新允许在安全中心里重新开启，不需要重装」；社区仍有相反经验，所以别把它当可靠开关用。

长期唯一的“正规”解法是买代码签名证书（受信任 CA，一年几百到几千元），不会为了免费工具去做。

### ❓ 支持哪些游戏版本？
Steam 版、Microsoft Store / Game Pass 版都可以，理论上所有 PC 版通用。

### ❓ 需要装 Python 吗？
不需要。下载的是打包好的单文件 exe，双击就能跑。只有想从源码运行才需要 Python。

### ❓ 为什么某个存档位「背包是空的」？
那些道具可能在**尸体背包**里 —— 角色阵亡后掉落的物品存在另一张 256 格表（`0x31170`）。本工具只读展示这部分，不会混进背包，也不会写进去。

### ❓ 武器为什么没有「数量」？
武器是独立表，字段是 `id / 等级 / …`，没有堆叠概念。等级 1–4 对应游戏内的强化等级。

### ❓ 道具列表不全怎么办？
目前收录 221 个道具 + 39 把武器。发现缺失欢迎提 [Issue](https://github.com/1jiulaoye/nieR-automata-save-editor/issues)，附上「道具名 + 在存档里看到的 ID」即可补表。

已知未收录：真实存档里出现过 1 个 ID `0x1F56`（数量 1），暂时显示为「未知」。

### ❓ 备份会不会覆盖掉？
不会。文件名带 opid（微秒时间戳 + 随机段），同一秒多次备份也是不同文件。

### ❓ 存档会不会被写坏？
见上一节「它怎么保证不写坏存档」。另外任何写入前都会先备份，出问题可以用「备份 ▾ → 恢复备份」回滚。

---

## 存档文件结构

`GameData.dat` 和 `SlotData_#.dat` 共用同一套偏移（前 4 字节不同：GameData 是 Steam 账号 ID，SlotData 是 0）。

```
0x00004  Steam 账号 ID / 0
0x3056C  金币            uint32 LE
0x30570  背包道具         256 条 × 12 字节
             +0x00  道具 ID     uint16 LE（0xFFFF 为空槽）
             +0x02  填充        4 字节
             +0x06  固定标记    07 00
             +0x08  数量        uint8（最大 255）
             +0x09  填充        3 字节
0x31170  尸体背包         256 条 × 12 字节（结构同上）
0x31D70  武器表           39 条 × 20 字节（5 个 int32）
             id / level(1-4) / new_item / new_story / enemies_defeated
             id = -1 表示空槽
0x324BC  芯片表           256 条 × 48 字节（12 个 int32）
             +0x00  chip_id_1 / chip_id_2 / type_id
             +0x0C  等级       int32
             +0x10  占用格数    int32
             +0x14  坐标 x/y/z  3 × int32
             +0x20  填充       4 × int32（空槽全 0xFF）
0x3871C  经验值           uint32 LE
```

普通芯片的 ID 规律：`chip_id_1 = 基址 + 等级`、`chip_id_2 = 基址 + 等级`，`type_id` 固定；等级 0–8 对应最小格数 4 / 5 / 6 / 7 / 9 / 11 / 14 / 17 / 21。

### 项目结构

```
nier-save-editor/
├── nier_editor.py      # 主界面（GUI + 事件）
├── save_io.py          # 存档读写（解析 + 事务写入 + 备份 + manifest）
├── chip_data.py        # 芯片表（31 普通 × 9 等级 + 19 系统 + 效果）
├── item_data.py        # 道具 221 + 武器 39 名称表 + 分类区间
├── constants.py        # 偏移量 / 记录大小 / 容量
├── selftest.py         # 自检（198 项，不需要游戏本体）
├── docs/index.html     # 展示页
├── requirements.txt
├── LICENSE
└── README.md
```

---

## 从源码运行 / 自行编译

```bash
# 1. 克隆
git clone https://github.com/1jiulaoye/nieR-automata-save-editor.git
cd nieR-automata-save-editor

# 2. 依赖（只有一个）
pip install "ttkbootstrap>=1.10,<3"

# 3. 直接运行
python nier_editor.py

# 4. 跑自检（198 项）
python selftest.py
```

Windows 上打包成单文件 exe：

```bat
pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed ^
  --name nier-save-editor --collect-all ttkbootstrap nier_editor.py
```

Linux 上交叉编译 Windows exe（v1.4.0 的包就是这么出的）：

```bash
sudo apt install wine64 wine32:i386
wine python-3.11.9-amd64.exe /quiet InstallAllUsers=0 TargetDir=C:\\Py311
wine "C:\\Py311\\python.exe" -m pip install ttkbootstrap==2.2.3 pyinstaller
wine "C:\\Py311\\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed \
  --name nier-save-editor --collect-all ttkbootstrap nier_editor.py
```

技术栈：Python 3.11 + Tkinter（ttkbootstrap 主题）+ PyInstaller 单文件打包。

---

## 数据来源与验证

道具 / 武器 ID 与名称来自社区实测表：

- [MysteryDash/NieR.Automata.Editor](https://github.com/MysteryDash/NieR.Automata.Editor) 的 `Item.cs` / `Weapon.cs` / `Save.cs`（221 道具 + 39 武器 + 存档布局）
- [CensoredUsername/Nier-Automata-editor](https://github.com/CensoredUsername/Nier-Automata-editor) 的 `ADDRESS.md`（偏移量、芯片表）
- 中文名为社区通行译名（本作没有官方中文）

验证方式：

1. 用真实存档（397,683 字节 `GameData` + 397,683 / 235,980 字节 `SlotData`）逐项核对：背包 64 件、武器 9 把、芯片 151 条，名称全部能识别
2. 改一项 → 写盘 → 回读 → **逐字节 diff**：金币只动 `0x3056C`、加道具只落在背包区、加芯片只落在芯片区、改武器等级只动该记录第 2 个 int32
3. 文件大小不变、无残留 `.tmp`、原始存档 sha256 不变
4. `selftest.py` 198 项全过

> 说明：exe 在 Linux 上通过 Wine 交叉编译，界面在 Windows 实机上的最终观感请以你实际打开为准。

---

## 版本历史

> 每个版本具体改了什么（含 v1.3 → v1.4.0 的逐项对比）见 [CHANGELOG.md](CHANGELOG.md)。

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v1.4.0 | 2026-10 | 🎉 首个公开发布版。按真实存档重构布局（背包 256 / 尸体背包 / 武器表 39×20B / 芯片 256）；数据核对补 107 个道具 + 39 把武器；两阶段事务写入 + opid 备份 + manifest；恢复原子化；界面重做为简洁风格，更名「尼尔存档修改器」 |
| v1.3 | 2026-05 | 修复数据同步：金币 / 道具以 SlotData 为准；切换存档提示保存 |
| v1.2 | 2026-05 | 修复芯片数据解析（48 字节对齐）；添加芯片效果展示 |
| v1.1 | 2026-05 | 修复保存时文件膨胀问题；稳定性优化 |
| v1.0 | 2026-05 | 首次发布：金币 / 道具 / 芯片，多存档位 |

---

## 反馈与贡献

- Bug、缺的道具、想要的功能：[提 Issue](https://github.com/1jiulaoye/nieR-automata-save-editor/issues)
- 代码改动：欢迎 PR，提交前请跑一遍 `python selftest.py`
- 其他工具与 Mod：[小柒的百宝箱](https://keaixiaoqi.cn)
- 相关社区：[Nexus Mods](https://www.nexusmods.com/nierautomata) · [NieR:Automata Wiki](https://nierautomata.fandom.com/)

---

## 免责声明

- 本项目是个人自用工具，**不承诺长期维护**；Issue 和 PR 随缘处理，能修就修
- 基于 MIT 许可证开源，仅供学习交流
- 修改存档可能影响游戏体验，请自行评估风险；工具会尽力备份，但**请自己再留一份原始存档**
- 本工具完全免费，如遇收费下载请警惕
- 请支持正版《尼尔：机械纪元》

> 🐱 Made by 小柒 ·「为了人类的荣耀——以及更轻松的游戏体验」
