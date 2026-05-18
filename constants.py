"""
小柒尼尔存档修改器 — 偏移量常量
基于 Nier-Automata-editor ADDRESS.md + chips.py 实测数据
"""

# --- 存档路径 ---
SAVE_FOLDER_NAME = "NieR_Automata"
SAVE_PARENT = "My Games"  # 相对于 Documents
GAMEDATA_FILE = "GameData.dat"
SLOT_FILES = ("SlotData_0.dat", "SlotData_1.dat", "SlotData_2.dat")

# --- GameData.dat 偏移量 ---
OFFSET_MONEY = 0x3056C          # 金币, uint32 LE
OFFSET_EXPERIENCE = 0x3871C     # 经验值, uint32 LE
OFFSET_ITEMS_START = 0x30570    # 道具区起始
OFFSET_ITEMS_END = 0x6116F      # GameData 道具区结束

ITEM_RECORD_SIZE = 12           # 每条道具 12 字节

# SlotData 道具区（游戏实际读取）：只有 512 条道具记录
SLOT_MAX_ITEMS = 512
SLOT_ITEMS_END = OFFSET_ITEMS_START + SLOT_MAX_ITEMS * ITEM_RECORD_SIZE  # 0x31D70
assert SLOT_ITEMS_END == 0x31D70, f"SLOT_ITEMS_END 计算错误: 0x{SLOT_ITEMS_END:X}"
SLOT_MONEY_ITEMS_SIZE = SLOT_ITEMS_END - OFFSET_MONEY  # 金币 + 512 道具 = 6,148 字节
ITEM_FLAG_BYTES = b'\x07\x00'   # +0x06 固定标记
ITEM_EMPTY_ID = 0xFFFF          # 空槽位的 Item ID
MAX_ITEMS = (OFFSET_ITEMS_END - OFFSET_ITEMS_START) // ITEM_RECORD_SIZE

# --- SlotData_X.dat 偏移量 ---
OFFSET_CHIPS_START = 0x324BC    # 芯片区起始 (chips.py 实测)
CHIP_RECORD_SIZE = 48           # 每条芯片 48 字节 (12×int32)
MAX_CHIPS = 512                 # 安全上限
CHIP_EMPTY_MARKER = 0xFFFFFFFF  # 空芯片前三 int32 全为这个值

# --- 数值约束 ---
MAX_MONEY = 2**32 - 1           # 4,294,967,295
MAX_ITEM_AMOUNT = 255           # uint8
