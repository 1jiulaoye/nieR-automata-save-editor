"""
NieR Automata 存档读写模块
支持 GameData.dat（金币+道具）和 SlotData_X.dat（芯片）
"""

import os
import struct
import shutil
from datetime import datetime
from constants import *


class SaveFile:
    """封装存档文件的二进制读写"""

    # 不同文件类型的安全大小
    _MIN_SAFE_SIZE: int = OFFSET_ITEMS_END + 4  # 0x61173 = 397,683 (GameData)
    _SLOT_SAFE_SIZE: int = OFFSET_CHIPS_START + MAX_CHIPS * CHIP_RECORD_SIZE  # 0x324BC + 512*48 = 230,588

    def __init__(self, filepath: str):
        self.filepath = filepath
        with open(filepath, 'rb') as f:
            raw = f.read()
        self._original_size = len(raw)
        self._data = bytearray(raw)
        # 判断文件类型，使用不同的安全大小
        fname = os.path.basename(filepath).lower()
        if fname.startswith('slotdata'):
            safe_size = self._SLOT_SAFE_SIZE
        else:
            safe_size = self._MIN_SAFE_SIZE
        # 极小存档自动零填充到安全大小
        if len(self._data) < safe_size:
            self._data.extend(b'\x00' * (safe_size - len(self._data)))
        self._modified = False
        self._save_size = max(self._original_size, safe_size)

    def _check_bounds(self, offset: int, size: int, name: str = "") -> None:
        """边界检查，越界时抛出明确的 ValueError"""
        if offset + size > len(self._data):
            raise ValueError(
                f"{name or '操作'}: 偏移 0x{offset:X}+{size} 超出存档大小 {len(self._data):,} 字节"
            )

    # ======================== 金币 ========================

    def get_money(self) -> int:
        return struct.unpack_from('<I', self._data, OFFSET_MONEY)[0]

    def set_money(self, amount: int):
        if not (0 <= amount <= MAX_MONEY):
            raise ValueError(f"Money must be 0-{MAX_MONEY}")
        struct.pack_into('<I', self._data, OFFSET_MONEY, amount)
        self._modified = True

    # ======================== 道具 ========================

    def get_items(self, limit: int = MAX_ITEMS) -> list[tuple[int, int]]:
        """返回所有道具: [(item_id, amount), ...] (最多 limit 条)"""
        items = []
        for i in range(min(limit, MAX_ITEMS)):
            offset = OFFSET_ITEMS_START + i * ITEM_RECORD_SIZE
            self._check_bounds(offset, ITEM_RECORD_SIZE, f"读取道具[{i}]")
            item_id = struct.unpack_from('<H', self._data, offset)[0]
            amount = self._data[offset + 8]
            items.append((item_id, amount))
        return items

    def get_owned_items(self) -> list[tuple[int, int]]:
        """只返回数量 > 0 的道具（排除空槽和未初始化槽）"""
        return [(iid, amt) for iid, amt in self.get_items()
                if amt > 0 and iid != ITEM_EMPTY_ID and iid != 0]

    def get_item(self, item_id: int) -> int:
        """查找指定道具的数量（第一个匹配），找不到返回0"""
        for i in range(MAX_ITEMS):
            offset = OFFSET_ITEMS_START + i * ITEM_RECORD_SIZE
            sid = struct.unpack_from('<H', self._data, offset)[0]
            if sid == item_id:
                return self._data[offset + 8]
        return 0

    def set_item(self, index: int, item_id: int, amount: int):
        """写入指定位置的道具"""
        if not (0 <= amount <= MAX_ITEM_AMOUNT):
            raise ValueError(f"Amount must be 0-{MAX_ITEM_AMOUNT}")
        offset = OFFSET_ITEMS_START + index * ITEM_RECORD_SIZE
        struct.pack_into('<H', self._data, offset, item_id)
        self._data[offset + 2:offset + 6] = b'\x00' * 4
        self._data[offset + 6:offset + 8] = ITEM_FLAG_BYTES
        self._data[offset + 8] = amount
        self._data[offset + 9:offset + 12] = b'\x00' * 3
        self._modified = True

    def add_or_update_item(self, item_id: int, amount: int = 1, limit: int = MAX_ITEMS) -> bool:
        """添加道具（找到已有条目则增加数量，否则写入空槽）。limit 限制搜索范围。返回是否成功"""
        max_search = min(limit, MAX_ITEMS)
        # 先找已有条目
        for i in range(max_search):
            offset = OFFSET_ITEMS_START + i * ITEM_RECORD_SIZE
            sid = struct.unpack_from('<H', self._data, offset)[0]
            if sid == item_id:
                current = self._data[offset + 8]
                new_amt = min(current + amount, MAX_ITEM_AMOUNT)
                self._data[offset + 8] = new_amt
                self._modified = True
                return True
        # 找空槽位（只认 0xFFFF 为空，0x0000 是合法道具 Small Recovery）
        for i in range(max_search):
            offset = OFFSET_ITEMS_START + i * ITEM_RECORD_SIZE
            sid = struct.unpack_from('<H', self._data, offset)[0]
            if sid == ITEM_EMPTY_ID:
                self.set_item(i, item_id, min(amount, MAX_ITEM_AMOUNT))
                return True
        return False  # 没空位了

    # ======================== 跨文件同步 ========================

    def sync_money_items_from(self, source: 'SaveFile'):
        """
        从源存档同步金币+道具数据到本存档。
        金币和道具存储在相同偏移处，但 SlotData 只存 512 条（SLOT_MAX_ITEMS）。
        """
        items_size = SLOT_MAX_ITEMS * ITEM_RECORD_SIZE  # 6,144 字节
        end_offset = OFFSET_ITEMS_START + items_size  # 0x31D70

        # 边界检查
        source._check_bounds(OFFSET_MONEY, 4, "同步金币源数据")
        source._check_bounds(OFFSET_ITEMS_START, items_size, "同步道具源数据")

        # 确保目标（本对象）足够大
        if len(self._data) < end_offset:
            self._data.extend(b'\x00' * (end_offset - len(self._data)))
            if end_offset > self._save_size:
                self._save_size = end_offset

        # 复制金币 (4 字节)
        self._data[OFFSET_MONEY:OFFSET_MONEY + 4] = source._data[OFFSET_MONEY:OFFSET_MONEY + 4]

        # 复制道具区 (512 条 × 12 字节)
        self._data[OFFSET_ITEMS_START:end_offset] = source._data[OFFSET_ITEMS_START:end_offset]

        self._modified = True

    # ======================== 芯片 (SlotData only) ========================

    def get_chips(self) -> list[dict]:
        """返回所有芯片记录（含空槽）"""
        chips = []
        for i in range(MAX_CHIPS):
            offset = OFFSET_CHIPS_START + i * CHIP_RECORD_SIZE
            raw = self._data[offset:offset + CHIP_RECORD_SIZE]
            cid1, cid2, cid3, lv, sz, ox, oy, oz, p1, p2, p3, p4 = struct.unpack_from('<12i', raw)
            chips.append({
                'index': i,
                'raw': bytes(raw),
                'empty': (cid1 == -1 and cid2 == -1 and cid3 == -1),
                'chip_id_1': cid1,
                'chip_id_2': cid2,
                'type_id': cid3,
                'level': lv,
                'size': sz,
                'offset_x': ox,
                'offset_y': oy,
                'offset_z': oz,
            })
        return chips

    def get_installed_chips(self) -> list[dict]:
        """只返回已安装的芯片（非空）"""
        return [c for c in self.get_chips() if not c['empty']]

    def add_chip(self, chip_bytes: bytes) -> bool:
        """添加芯片到第一个空槽，返回是否成功"""
        if len(chip_bytes) != CHIP_RECORD_SIZE:
            raise ValueError(f"Chip data must be {CHIP_RECORD_SIZE} bytes")
        for i in range(MAX_CHIPS):
            offset = OFFSET_CHIPS_START + i * CHIP_RECORD_SIZE
            cid1, cid2, cid3 = struct.unpack_from('<3i', self._data, offset)
            if cid1 == -1 and cid2 == -1 and cid3 == -1:  # 空槽（与 get_chips() 一致）
                self._data[offset:offset + CHIP_RECORD_SIZE] = chip_bytes
                self._modified = True
                return True
        return False

    def remove_chip(self, index: int):
        """删除指定位置的芯片（写空记录）"""
        if not (0 <= index < MAX_CHIPS):
            raise IndexError(f"Chip index must be 0-{MAX_CHIPS-1}")
        offset = OFFSET_CHIPS_START + index * CHIP_RECORD_SIZE
        empty = b'\xff' * 44 + b'\x00' * 4
        self._data[offset:offset + CHIP_RECORD_SIZE] = empty
        self._modified = True

    def set_chip(self, index: int, chip_bytes: bytes):
        """替换指定位置的芯片"""
        if not (0 <= index < MAX_CHIPS):
            raise IndexError(f"Chip index must be 0-{MAX_CHIPS-1}")
        if len(chip_bytes) != CHIP_RECORD_SIZE:
            raise ValueError(f"Chip data must be {CHIP_RECORD_SIZE} bytes")
        offset = OFFSET_CHIPS_START + index * CHIP_RECORD_SIZE
        self._data[offset:offset + CHIP_RECORD_SIZE] = chip_bytes
        self._modified = True

    # ======================== 持久化 ========================

    def save(self):
        """保存到原文件（按文件类型写入合适大小）"""
        with open(self.filepath, 'wb') as f:
            f.write(self._data[:self._save_size])
        self._modified = False

    def backup(self, backup_dir: str) -> str:
        """创建带时间戳的备份，返回备份路径"""
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = os.path.basename(self.filepath)
        name, ext = os.path.splitext(fname)
        target = os.path.join(backup_dir, f"{name}_{ts}{ext}")
        shutil.copy2(self.filepath, target)
        return target

    @property
    def modified(self) -> bool:
        return self._modified

    @property
    def file_size(self) -> int:
        return len(self._data)
