"""
小柒尼尔存档修改器 — 偏移量常量

权威布局来自 MysteryDash/NieR.Automata.Editor 的 Save.cs，并已用真实存档逐项验证：

    0x30570  背包道具      256 条 × 12B  = 0x0C00
    0x31170  尸体背包      256 条 × 12B  = 0x0C00（只读展示）
    0x31D70  武器表         39 条 × 20B  = 0x030C
    0x324BC  芯片表        256 条 × 48B  = 0x3000

旧版本把尸体背包误当成背包后半段，芯片也误读了 256 条后面的其它数据。
本模块只提供权威的 256 条背包 / 256 条尸体背包 / 39 条武器 / 256 条芯片容量。
"""

# --- 存档路径 ---
SAVE_FOLDER_NAME = "NieR_Automata"
SAVE_PARENT = "My Games"  # 相对于 Documents
GAMEDATA_FILE = "GameData.dat"
SLOT_FILES = ("SlotData_0.dat", "SlotData_1.dat", "SlotData_2.dat")

# --- GameData.dat 偏移量 ---
OFFSET_MONEY = 0x3056C          # 金币, uint32 LE
OFFSET_EXPERIENCE = 0x3871C     # 经验值, uint32 LE
OFFSET_ITEMS_START = 0x30570    # 背包道具区起始
OFFSET_ITEMS_END = 0x6116F      # GameData 道具区结束（文件最小长度校验用）

ITEM_RECORD_SIZE = 12           # 每条道具 12 字节

# --- 背包道具（权威：256 条，尸体背包是独立区域）---
ITEMS_COUNT = 256
ITEMS_END = OFFSET_ITEMS_START + ITEMS_COUNT * ITEM_RECORD_SIZE  # 0x31170
assert ITEMS_END == 0x31170, f"ITEMS_END 计算错误: 0x{ITEMS_END:X}"

# --- 尸体背包（只读展示，绝不参与背包写入 / 同步）---
CORPSE_ITEMS_START = 0x31170
CORPSE_ITEMS_COUNT = 256
CORPSE_ITEMS_END = CORPSE_ITEMS_START + CORPSE_ITEMS_COUNT * ITEM_RECORD_SIZE  # 0x31D70
assert CORPSE_ITEMS_END == 0x31D70, (
    f"CORPSE_ITEMS_END 计算错误: 0x{CORPSE_ITEMS_END:X}"
)

# --- 武器表（39 条 × 5 个 int32）---
WEAPONS_START = 0x31D70
WEAPONS_COUNT = 39
WEAPON_RECORD_SIZE = 20
WEAPONS_END = WEAPONS_START + WEAPONS_COUNT * WEAPON_RECORD_SIZE  # 0x3207C
assert WEAPONS_END == 0x3207C, f"WEAPONS_END 计算错误: 0x{WEAPONS_END:X}"

# --- 芯片表（256 条，空槽判定保持「全 0xFF 或整条全 0」）---
OFFSET_CHIPS_START = 0x324BC
CHIP_RECORD_SIZE = 48
CHIPS_COUNT = 256
CHIPS_END = OFFSET_CHIPS_START + CHIPS_COUNT * CHIP_RECORD_SIZE  # 0x354BC
assert CHIPS_END == 0x354BC, f"CHIPS_END 计算错误: 0x{CHIPS_END:X}"
CHIP_EMPTY_MARKER = 0xFFFFFFFF

ITEM_FLAG_BYTES = b'\x07\x00'   # +0x06 固定标记（Status = 0x00070000）
ITEM_EMPTY_ID = 0xFFFF          # 空槽位的 Item ID（int32 -1 的低 16 位）

# --- 兼容旧常量名：语义已收窄为 256 ---
SLOT_MAX_ITEMS = ITEMS_COUNT
MAX_ITEMS = ITEMS_COUNT
MAX_CHIPS = CHIPS_COUNT
SLOT_ITEMS_END = ITEMS_END
SLOT_MONEY_ITEMS_SIZE = ITEMS_END - OFFSET_MONEY  # 金币 + 256 背包道具 = 3,076 字节

# --- 数值约束 ---
MAX_MONEY = 2**32 - 1           # 4,294,967,295
MAX_ITEM_AMOUNT = 255           # uint8
WEAPON_LEVEL_MIN = 1
WEAPON_LEVEL_MAX = 4
