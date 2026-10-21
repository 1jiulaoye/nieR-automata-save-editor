"""
NieR Automata 存档读写模块
支持 GameData.dat（金币+道具）和 SlotData_X.dat（芯片）
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import struct
from datetime import datetime
from constants import *
from item_data import WEAPON_NAMES, get_weapon_name


class SaveError(Exception):
    """存档读写错误（文件不合法 / 写入失败）"""


# 备份清单：每个操作（同一 opid）对应一条记录
BACKUP_MANIFEST_NAME = "manifest.json"
_LEGACY_BACKUP_RE = re.compile(
    r"^(?P<base>GameData|SlotData_\d+)_(?P<ts>\d{8}_\d{6})\.dat$", re.IGNORECASE
)
_OPID_BACKUP_RE = re.compile(
    r"^(?P<base>GameData|SlotData_\d+)_"
    r"(?P<opid>\d{8}_\d{6}_\d{6}_[0-9a-fA-F]{4})\.dat$",
    re.IGNORECASE,
)


def new_operation_id() -> str:
    """生成一次备份/保存操作的唯一 id：微秒时间戳 + 4 位随机十六进制。"""
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{secrets.token_hex(2)}"


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slot_from_filename(name: str) -> int | None:
    """从 SlotData_<n>.dat 推断槽位号；GameData 等返回 None。"""
    base = os.path.basename(name)
    m = re.match(r"^SlotData_(\d+)\.dat$", base, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _fsync_dir(path: str) -> None:
    """尽量 fsync 父目录；Windows 等不支持目录 fsync 的平台忽略即可。"""
    try:
        fd = os.open(path or ".", os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def load_backup_manifest(backup_dir: str) -> dict:
    """读取 manifest.json；文件不存在时返回空清单（兼容旧备份）。"""
    path = os.path.join(backup_dir, BACKUP_MANIFEST_NAME)
    if not os.path.isfile(path):
        return {"version": 1, "operations": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise SaveError(f"备份清单损坏，无法安全恢复：{path}\n{e}") from e
    if not isinstance(data, dict):
        raise SaveError(f"备份清单格式不正确：{path}")
    ops = data.get("operations")
    if isinstance(ops, dict):
        # 兼容键值对形式
        data["operations"] = [
            dict(op, opid=opid) if isinstance(op, dict) else {"opid": opid}
            for opid, op in ops.items()
        ]
    elif not isinstance(ops, list):
        data["operations"] = []
    return data


def _write_backup_manifest(backup_dir: str, manifest: dict) -> None:
    """原子写入 manifest（先写 .tmp + fsync，再 os.replace）。"""
    os.makedirs(backup_dir, exist_ok=True)
    path = os.path.join(backup_dir, BACKUP_MANIFEST_NAME)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _fsync_dir(backup_dir)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def _manifest_file_map(op: dict) -> dict[str, dict]:
    """把 manifest 中 files（列表或字典）统一成 {原始文件名: 条目}。"""
    raw = op.get("files") or []
    mapping: dict[str, dict] = {}
    if isinstance(raw, dict):
        for source, item in raw.items():
            if isinstance(item, dict):
                mapping[source] = item
            else:
                mapping[source] = {"path": item}
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            source = item.get("source") or item.get("name")
            if source:
                mapping[source] = item
    return mapping


def find_backup_pairs(backup_dir: str, slot_index: int) -> list[dict]:
    """找出可用于恢复的成对备份，返回按操作时间倒序排列的列表。

    规则：
    - 新式备份必须来自同一个 opid，且同时包含 GameData.dat 与当前槽位的
      SlotData_<slot>.dat；manifest 中有 sha256 时还会校验实际文件。
    - 没有 manifest 的旧备份按秒级时间戳分组兜底，同样必须同组且包含当前槽位；
      配不上就返回空列表，绝不跨组/跨槽混搭。
    - 即使 manifest 被删，新式文件名本身仍带 opid，也按 opid 兜底配对。
    """
    if not os.path.isdir(backup_dir):
        return []
    slot_file = SLOT_FILES[slot_index]
    slot_base = os.path.splitext(slot_file)[0]
    pairs: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add_pair(opid: str, time_text: str, source: str,
                 gd_name: str, sd_name: str,
                 gd_sha: str | None = None, sd_sha: str | None = None) -> None:
        key = (gd_name, sd_name)
        if key in seen:
            return
        gd_path = os.path.join(backup_dir, gd_name)
        sd_path = os.path.join(backup_dir, sd_name)
        if not (os.path.isfile(gd_path) and os.path.isfile(sd_path)):
            return
        if gd_sha and _file_sha256(gd_path) != gd_sha:
            return
        if sd_sha and _file_sha256(sd_path) != sd_sha:
            return
        seen.add(key)
        pairs.append({
            "opid": opid,
            "time": time_text,
            "slot": slot_index,
            "source": source,
            "gamedata": gd_path,
            "slotdata": sd_path,
            "gamedata_name": gd_name,
            "slotdata_name": sd_name,
        })

    # 1) 有 manifest 的新式备份：只认同一 opid 且包含当前槽位 SlotData 的记录
    try:
        manifest = load_backup_manifest(backup_dir)
    except SaveError:
        manifest = {"operations": []}
    for op in manifest.get("operations", []):
        if not isinstance(op, dict):
            continue
        opid = op.get("opid")
        if not opid:
            continue
        if op.get("slot") is not None and op.get("slot") != slot_index:
            continue
        files = _manifest_file_map(op)
        if "GameData.dat" not in files or slot_file not in files:
            continue
        # 一次操作只能对应一个槽位，避免人工构造的 manifest 让 GameData 跨槽混搭
        slot_keys = [k for k in files if k.lower().startswith("slotdata_")]
        if len(slot_keys) != 1 or slot_keys[0].lower() != slot_file.lower():
            continue
        gd_item = files["GameData.dat"]
        sd_item = files[slot_file]
        gd_name = gd_item.get("path") or gd_item.get("backup") or gd_item.get("name")
        sd_name = sd_item.get("path") or sd_item.get("backup") or sd_item.get("name")
        if not gd_name or not sd_name:
            continue
        time_text = op.get("time") or op.get("timestamp") or str(opid)
        add_pair(str(opid), str(time_text), "manifest", gd_name, sd_name,
                 gd_item.get("sha256"), sd_item.get("sha256"))

    # 2) 没有 manifest 的旧式备份：按秒级时间戳分组兜底
    legacy_groups: dict[str, dict[str, str]] = {}
    opid_groups: dict[str, dict[str, str]] = {}
    for name in os.listdir(backup_dir):
        m = _LEGACY_BACKUP_RE.match(name)
        if m:
            base = m.group("base")
            if base.lower() == "gamedata":
                base = "GameData"
            legacy_groups.setdefault(m.group("ts"), {}).setdefault(base, name)
            continue
        m = _OPID_BACKUP_RE.match(name)
        if m:
            base = m.group("base")
            if base.lower() == "gamedata":
                base = "GameData"
            opid_groups.setdefault(m.group("opid"), {}).setdefault(base, name)

    def legacy_pair(files: dict[str, str]) -> tuple[str, str] | None:
        """旧备份同一秒内若出现多个 SlotData，无法判断 GameData 属于哪个槽位，
        必须拒绝配对，避免把别的槽位 GameData 混进来。"""
        slot_keys = [k for k in files if k.lower().startswith("slotdata_")]
        if "GameData" not in files or len(slot_keys) != 1:
            return None
        key = slot_keys[0]
        if key.lower() != slot_base.lower():
            return None
        return files["GameData"], files[key]

    for ts, files in legacy_groups.items():
        matched = legacy_pair(files)
        if matched:
            gd_name, sd_name = matched
            try:
                time_text = datetime.strptime(ts, "%Y%m%d_%H%M%S").isoformat(" ")
            except ValueError:
                time_text = ts
            add_pair(ts, time_text, "legacy", gd_name, sd_name)

    for opid, files in opid_groups.items():
        matched = legacy_pair(files)
        if matched:
            add_pair(opid, opid, "filename", matched[0], matched[1])

    pairs.sort(key=lambda p: str(p["opid"]), reverse=True)
    return pairs


def _stage_copy(src: str, dst: str) -> str:
    """把 src 复制到 dst 同目录临时文件并 fsync，返回临时文件路径。"""
    tmp = dst + ".restore.tmp"
    try:
        with open(src, "rb") as rf, open(tmp, "wb") as wf:
            shutil.copyfileobj(rf, wf, 1024 * 1024)
            wf.flush()
            os.fsync(wf.fileno())
        try:
            shutil.copystat(src, tmp)
        except OSError:
            pass
        return tmp
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def replace_files_atomically(file_pairs: list[tuple[str, str]]) -> None:
    """两阶段替换：先把所有源文件复制到临时文件，全部成功后再逐个 os.replace。

    任一阶段失败都会清理临时文件并抛出；已经 replace 的文件由调用方用快照回滚。
    """
    staged: list[tuple[str, str]] = []
    try:
        for src, dst in file_pairs:
            staged.append((_stage_copy(src, dst), dst))
        for tmp, dst in staged:
            os.replace(tmp, dst)
            _fsync_dir(os.path.dirname(os.path.abspath(dst)))
    except Exception:
        for tmp, _dst in staged:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        raise


class SaveFile:
    """封装存档文件的二进制读写"""

    # 不同文件类型需要的最小大小（小于它就说明不是有效存档，宁可拒绝也不要猜）
    _MIN_SAFE_SIZE: int = OFFSET_ITEMS_END + 4  # 0x61173 = 397,683 (GameData)
    _SLOT_SAFE_SIZE: int = CHIPS_END  # 0x354BC = 218,300（256 条芯片）

    def __init__(self, filepath: str):
        self.filepath = filepath
        with open(filepath, 'rb') as f:
            raw = f.read()
        self._original_size = len(raw)
        self._data = bytearray(raw)
        # 判断文件类型，使用不同的安全大小
        fname = os.path.basename(filepath).lower()
        is_slot = fname.startswith('slotdata')
        required = self._SLOT_SAFE_SIZE if is_slot else self._MIN_SAFE_SIZE
        if self._original_size < required:
            raise SaveError(
                f"{fname} 只有 {self._original_size:,} 字节，"
                f"小于该类型存档的最小长度 {required:,} 字节。\n"
                f"这可能不是有效的尼尔存档，或文件已被截断 —— 已拒绝载入，未做任何修改。"
            )
        self._modified = False
        # 两阶段保存：prepare() 生成的临时文件路径，commit()/abort() 后清空
        self._pending_tmp: str | None = None
        # 永远按原文件长度写回，绝不静默扩容
        self._save_size = self._original_size

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

    # ======================== 背包道具 ========================

    def _max_items(self) -> int:
        """当前文件实际能容纳的背包记录数；权威上限固定为 256。"""
        usable = max(0, (len(self._data) - OFFSET_ITEMS_START) // ITEM_RECORD_SIZE)
        return min(ITEMS_COUNT, usable)

    def get_items(self, limit: int = ITEMS_COUNT) -> list[tuple[int, int]]:
        """返回背包 256 条记录: [(item_id, amount), ...]。

        只读 0x30570..0x31170 的背包区；0x31170 起的尸体背包必须用
        get_corpse_items() 单独读取，绝不混进这里。
        """
        items = []
        count = min(max(0, limit), ITEMS_COUNT, self._max_items())
        for i in range(count):
            offset = OFFSET_ITEMS_START + i * ITEM_RECORD_SIZE
            item_id = struct.unpack_from('<H', self._data, offset)[0]
            amount = self._data[offset + 8]
            items.append((item_id, amount))
        return items

    def get_owned_items(self) -> list[tuple[int, int]]:
        """只返回背包里数量 > 0 的道具。

        注意：item_id == 0 是小恢复药，是合法道具，不能按 0 过滤；
        空槽位的判定只认 0xFFFF 或数量 0。
        """
        return [(iid, amt) for iid, amt in self.get_items()
                if amt > 0 and iid != ITEM_EMPTY_ID]

    def get_item(self, item_id: int) -> int:
        """查找背包中指定道具的数量（第一个匹配），找不到返回 0。"""
        for i in range(self._max_items()):
            offset = OFFSET_ITEMS_START + i * ITEM_RECORD_SIZE
            sid = struct.unpack_from('<H', self._data, offset)[0]
            if sid == item_id:
                return self._data[offset + 8]
        return 0

    def set_item(self, index: int, item_id: int, amount: int):
        """写入背包指定位置；index 越界（含负数）抛 IndexError。"""
        if not (0 <= amount <= MAX_ITEM_AMOUNT):
            raise ValueError(f"Amount must be 0-{MAX_ITEM_AMOUNT}")
        max_items = self._max_items()
        if not (0 <= index < max_items):
            raise IndexError(
                f"Item index must be 0-{max_items - 1} for "
                f"{os.path.basename(self.filepath)}, got {index}"
            )
        offset = OFFSET_ITEMS_START + index * ITEM_RECORD_SIZE
        struct.pack_into('<H', self._data, offset, item_id)
        self._data[offset + 2:offset + 6] = b'\x00' * 4
        self._data[offset + 6:offset + 8] = ITEM_FLAG_BYTES
        self._data[offset + 8] = amount
        self._data[offset + 9:offset + 12] = b'\x00' * 3
        self._modified = True

    def add_or_update_item(self, item_id: int, amount: int = 1,
                           limit: int = ITEMS_COUNT) -> bool:
        """添加背包道具（已有则增加数量，否则写空槽）。limit 限制搜索范围。

        只搜索背包 256 条；尸体背包 / 武器表 / 芯片表绝不会被写入。

        返回值约定：
        - True：本次确实写入了新道具，或把已有道具的数量增加了至少 1；
        - False：道具已存在且数量已经是 255，或 256 条背包已无空位；
        - item_id / amount 非法时抛 ValueError（不写入任何数据）：
          item_id 必须为 0..0xFFFE（0xFFFF 是空槽标记，不允许写入），
          amount 必须为 1..255。
        """
        if not isinstance(item_id, int) or not (0 <= item_id < ITEM_EMPTY_ID):
            raise ValueError(
                f"item_id must be 0-{ITEM_EMPTY_ID - 1} (0xFFFF is the empty slot marker), "
                f"got {item_id!r}"
            )
        if not isinstance(amount, int) or not (1 <= amount <= MAX_ITEM_AMOUNT):
            raise ValueError(f"Amount must be 1-{MAX_ITEM_AMOUNT}, got {amount!r}")
        # 同时受调用方 limit、权威 256 条上限与文件实际容量限制。
        max_search = min(max(0, limit), ITEMS_COUNT, self._max_items())
        # 先找已有条目
        for i in range(max_search):
            offset = OFFSET_ITEMS_START + i * ITEM_RECORD_SIZE
            sid = struct.unpack_from('<H', self._data, offset)[0]
            if sid == item_id:
                current = self._data[offset + 8]
                if current >= MAX_ITEM_AMOUNT:
                    return False  # 已满 255，本次没有增加
                new_amt = min(current + amount, MAX_ITEM_AMOUNT)
                self._data[offset + 8] = new_amt
                self._modified = True
                return True
        # 找空槽位：优先 0xFFFF，其次「id=0 且数量=0」的未初始化槽
        # （0x0000 本身是小恢复药，只有数量为 0 时才算空）
        for empty_id, need_zero_amount in ((ITEM_EMPTY_ID, False), (0, True)):
            for i in range(max_search):
                offset = OFFSET_ITEMS_START + i * ITEM_RECORD_SIZE
                sid = struct.unpack_from('<H', self._data, offset)[0]
                if sid != empty_id:
                    continue
                if need_zero_amount and self._data[offset + 8] != 0:
                    continue
                self.set_item(i, item_id, min(amount, MAX_ITEM_AMOUNT))
                return True
        return False  # 没空位了

    # ======================== 尸体背包（只读） ========================

    def _max_corpse_items(self) -> int:
        usable = max(0, (len(self._data) - CORPSE_ITEMS_START) // ITEM_RECORD_SIZE)
        return min(CORPSE_ITEMS_COUNT, usable)

    def get_corpse_items(self) -> list[tuple[int, int]]:
        """返回尸体背包 256 条记录: [(item_id, amount), ...]（只读）。

        这是 0x31170..0x31D70 的独立区域，只用于展示；没有任何写入 API，
        也不会被 add_or_update_item() / sync_money_items_from() 触碰。
        """
        items = []
        for i in range(self._max_corpse_items()):
            offset = CORPSE_ITEMS_START + i * ITEM_RECORD_SIZE
            item_id = struct.unpack_from('<H', self._data, offset)[0]
            amount = self._data[offset + 8]
            items.append((item_id, amount))
        return items

    def get_owned_corpse_items(self) -> list[tuple[int, int]]:
        """只返回尸体背包里数量 > 0 的记录（只读展示用）。"""
        return [(iid, amt) for iid, amt in self.get_corpse_items()
                if amt > 0 and iid != ITEM_EMPTY_ID]

    # ======================== 武器表 ========================

    def _max_weapons(self) -> int:
        usable = max(0, (len(self._data) - WEAPONS_START) // WEAPON_RECORD_SIZE)
        return min(WEAPONS_COUNT, usable)

    @staticmethod
    def _weapon_is_empty(weapon_id: int) -> bool:
        """武器空槽。

        权威标记是 id == -1（整条 0xFFFFFFFF）。GameData 的武器区可能是
        全 0 占位而非 39 把武器之一，这种未知 id 也按空槽展示，避免把
        占位数据误报成「已获得」；写入时 add_weapon 仍只找 id == -1。
        """
        return weapon_id == -1 or weapon_id not in WEAPON_NAMES

    def _read_weapon(self, index: int) -> tuple[int, int, int, int, int]:
        offset = WEAPONS_START + index * WEAPON_RECORD_SIZE
        return struct.unpack_from('<5i', self._data, offset)

    def get_weapons(self) -> list[dict]:
        """返回武器表 39 条记录（含空槽），不修改任何数据。"""
        weapons = []
        for i in range(self._max_weapons()):
            wid, level, new_item, new_story, enemies = self._read_weapon(i)
            empty = self._weapon_is_empty(wid)
            weapons.append({
                'index': i,
                'id': wid,
                'name': '（空槽）' if wid == -1 else get_weapon_name(wid),
                'level': level,
                'new_item': new_item,
                'new_story': new_story,
                'enemies_defeated': enemies,
                'empty': empty,
            })
        return weapons

    def set_weapon_level(self, index: int, level: int):
        """只改指定武器记录的第 2 个 int32（等级）；等级限制 1..4。"""
        if not (0 <= index < self._max_weapons()):
            raise IndexError(
                f"Weapon index must be 0-{self._max_weapons() - 1} for "
                f"{os.path.basename(self.filepath)}, got {index}"
            )
        if not isinstance(level, int) or not (WEAPON_LEVEL_MIN <= level <= WEAPON_LEVEL_MAX):
            raise ValueError(
                f"Weapon level must be {WEAPON_LEVEL_MIN}-{WEAPON_LEVEL_MAX}, got {level!r}"
            )
        wid = self._read_weapon(index)[0]
        if self._weapon_is_empty(wid):
            raise ValueError(f"不能修改空武器槽的等级：index={index}")
        offset = WEAPONS_START + index * WEAPON_RECORD_SIZE
        struct.pack_into('<i', self._data, offset + 4, level)
        self._modified = True

    def add_weapon(self, weapon_id: int) -> bool:
        """把武器写到第一个 id == -1 的槽：level=1,new_item=1,new_story=1,enemies=0。"""
        if not isinstance(weapon_id, int) or weapon_id not in WEAPON_NAMES:
            raise ValueError(f"未知武器 ID: {weapon_id!r}")
        for i in range(self._max_weapons()):
            if self._read_weapon(i)[0] == -1:
                offset = WEAPONS_START + i * WEAPON_RECORD_SIZE
                struct.pack_into('<5i', self._data, offset,
                                 weapon_id, 1, 1, 1, 0)
                self._modified = True
                return True
        return False  # 39 个槽都被占用

    def remove_weapon(self, index: int):
        """删除指定武器：整条 20 字节写 0xFFFFFFFF。"""
        if not (0 <= index < self._max_weapons()):
            raise IndexError(
                f"Weapon index must be 0-{self._max_weapons() - 1} for "
                f"{os.path.basename(self.filepath)}, got {index}"
            )
        offset = WEAPONS_START + index * WEAPON_RECORD_SIZE
        self._data[offset:offset + WEAPON_RECORD_SIZE] = b'\xff' * WEAPON_RECORD_SIZE
        self._modified = True

    # ======================== 跨文件同步 ========================

    def sync_money_items_from(self, source: 'SaveFile'):
        """从源存档同步金币 + 背包 256 条道具到本存档。

        只复制 0x3056C..0x31170（金币 4B + 背包 256×12B）；
        尸体背包、武器表、芯片表一律不碰，文件长度也不变。
        """
        items_size = ITEMS_COUNT * ITEM_RECORD_SIZE  # 3,072 字节
        end_offset = OFFSET_ITEMS_START + items_size  # 0x31170

        # 边界检查
        source._check_bounds(OFFSET_MONEY, 4, "同步金币源数据")
        source._check_bounds(OFFSET_ITEMS_START, items_size, "同步背包道具源数据")

        # 目标文件必须原本就容纳完整金币+背包区；绝不扩容（保持文件长度不变量）
        if len(self._data) < end_offset:
            raise SaveError(
                f"{os.path.basename(self.filepath)} 长度不足：同步金币/背包道具需要至少 "
                f"{end_offset:,} 字节，当前只有 {len(self._data):,} 字节；"
                f"已拒绝同步，文件未被修改。"
            )

        # 复制金币 (4 字节)
        self._data[OFFSET_MONEY:OFFSET_MONEY + 4] = source._data[OFFSET_MONEY:OFFSET_MONEY + 4]

        # 只复制背包 256 条 × 12 字节，止于 0x31170
        self._data[OFFSET_ITEMS_START:end_offset] = source._data[OFFSET_ITEMS_START:end_offset]

        self._modified = True

    # ======================== 芯片 (SlotData only) ========================

    @staticmethod
    def _is_empty_chip(cid1: int, cid2: int, cid3: int,
                       level: int = 0, size: int = 0,
                       raw: bytes | None = None) -> bool:
        """空槽判定（A6）。

        - 前三个 int32 全为 -1（0xFF…）是 remove_chip 写入的空标记；
        - 否则只有整条 48 字节全 0 才算空；
        - level / size 任一非 0 时一律不算空，避免覆盖部分损坏/初始化的记录。
        """
        if cid1 == -1 and cid2 == -1 and cid3 == -1:
            return True
        if level != 0 or size != 0:
            return False
        if cid1 == 0 and cid2 == 0 and cid3 == 0:
            if raw is not None:
                return all(b == 0 for b in raw)
            return True
        return False

    def _max_chips(self) -> int:
        """当前文件实际能容纳的芯片记录数；权威上限固定为 256。"""
        usable = max(0, (len(self._data) - OFFSET_CHIPS_START) // CHIP_RECORD_SIZE)
        return min(CHIPS_COUNT, usable)

    def get_chips(self) -> list[dict]:
        """返回芯片表最多 256 条记录（含空槽），不再读取后面的其它数据。"""
        chips = []
        for i in range(self._max_chips()):
            offset = OFFSET_CHIPS_START + i * CHIP_RECORD_SIZE
            raw = self._data[offset:offset + CHIP_RECORD_SIZE]
            cid1, cid2, cid3, lv, sz, ox, oy, oz, p1, p2, p3, p4 = struct.unpack_from('<12i', raw)
            chips.append({
                'index': i,
                'raw': bytes(raw),
                'empty': self._is_empty_chip(cid1, cid2, cid3, lv, sz, bytes(raw)),
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
        for i in range(self._max_chips()):
            offset = OFFSET_CHIPS_START + i * CHIP_RECORD_SIZE
            raw = bytes(self._data[offset:offset + CHIP_RECORD_SIZE])
            cid1, cid2, cid3, lv, sz = struct.unpack_from('<5i', raw)
            if self._is_empty_chip(cid1, cid2, cid3, lv, sz, raw):
                self._data[offset:offset + CHIP_RECORD_SIZE] = chip_bytes
                self._modified = True
                return True
        return False

    def remove_chip(self, index: int):
        """删除指定位置的芯片（写空记录：全部 0xFF，判空与 add_chip 一致）。"""
        max_chips = self._max_chips()
        if not (0 <= index < max_chips):
            raise IndexError(
                f"Chip index must be 0-{max_chips - 1} for "
                f"{os.path.basename(self.filepath)}, got {index}"
            )
        offset = OFFSET_CHIPS_START + index * CHIP_RECORD_SIZE
        self._data[offset:offset + CHIP_RECORD_SIZE] = b'\xff' * CHIP_RECORD_SIZE
        self._modified = True

    def set_chip(self, index: int, chip_bytes: bytes):
        """替换指定位置的芯片。"""
        max_chips = self._max_chips()
        if not (0 <= index < max_chips):
            raise IndexError(
                f"Chip index must be 0-{max_chips - 1} for "
                f"{os.path.basename(self.filepath)}, got {index}"
            )
        if len(chip_bytes) != CHIP_RECORD_SIZE:
            raise ValueError(f"Chip data must be {CHIP_RECORD_SIZE} bytes")
        offset = OFFSET_CHIPS_START + index * CHIP_RECORD_SIZE
        self._data[offset:offset + CHIP_RECORD_SIZE] = chip_bytes
        self._modified = True

    # ======================== 持久化 ========================

    def prepare(self, tmp_path: str | None = None) -> str:
        """两阶段写入第一阶段：把当前数据写到临时文件并 fsync，返回临时路径。

        此时尚未改动原文件；调用 commit() 才会 os.replace。
        任一失败都会删除临时文件，不留下半截存档。
        """
        if getattr(self, "_pending_tmp", None):
            self.abort()
        tmp = tmp_path or (self.filepath + '.tmp')
        try:
            with open(tmp, 'wb') as f:
                f.write(self._data[:self._save_size])
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            raise
        self._pending_tmp = tmp
        return tmp

    # 等价别名：stage + commit
    def stage(self, tmp_path: str | None = None) -> str:
        return self.prepare(tmp_path)

    def commit(self):
        """两阶段写入第二阶段：把 prepare() 的临时文件 os.replace 到原文件。"""
        tmp = getattr(self, "_pending_tmp", None)
        if not tmp:
            raise SaveError("没有待提交的临时文件，请先调用 prepare()")
        try:
            os.replace(tmp, self.filepath)
            self._pending_tmp = None
            self._modified = False
            _fsync_dir(os.path.dirname(os.path.abspath(self.filepath)))
        except Exception:
            self.abort()
            raise

    def abort(self):
        """放弃 prepare() 的临时文件（原文件保持不变）。"""
        tmp = getattr(self, "_pending_tmp", None)
        self._pending_tmp = None
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

    def save(self):
        """原子写入：内部走 prepare() + commit()，对外行为保持不变。"""
        self.prepare()
        self.commit()

    def backup(self, backup_dir: str, opid: str | None = None,
               slot: int | None = None) -> str:
        """创建唯一命名的备份，返回备份路径。

        文件名：<原名>_<opid>.dat，例如 GameData_20260102_030405_123456_ab12.dat。
        同一次操作备份多个文件时可传入相同 opid；不传则自动生成（微秒 + 4 位随机）。
        manifest.json 记录 opid、槽位、文件列表、sha256 与时间。
        """
        os.makedirs(backup_dir, exist_ok=True)
        fname = os.path.basename(self.filepath)
        name, ext = os.path.splitext(fname)
        if slot is None:
            slot = _slot_from_filename(fname)
        auto_opid = opid is None
        if auto_opid:
            opid = new_operation_id()

        target = os.path.join(backup_dir, f"{name}_{opid}{ext}")
        # 自动生成的 opid 若碰撞则重试；调用方显式传入的 opid 冲突时拒绝覆盖
        if os.path.exists(target):
            if not auto_opid:
                raise SaveError(f"备份文件已存在，拒绝覆盖：{target}")
            for _ in range(100):
                opid = new_operation_id()
                target = os.path.join(backup_dir, f"{name}_{opid}{ext}")
                if not os.path.exists(target):
                    break
            else:
                raise SaveError("无法生成唯一的备份文件名，请检查系统随机源/时钟")

        src_sha = _file_sha256(self.filepath)
        shutil.copy2(self.filepath, target)
        dst_sha = _file_sha256(target)
        if src_sha != dst_sha:
            try:
                os.remove(target)
            except OSError:
                pass
            raise SaveError(f"备份校验失败：{target} 的内容与源文件不一致")

        now_text = datetime.now().isoformat(timespec="microseconds")
        manifest = load_backup_manifest(backup_dir)
        ops = manifest.setdefault("operations", [])
        op = next((x for x in ops
                   if isinstance(x, dict) and x.get("opid") == opid), None)
        if op is None:
            op = {"opid": opid, "time": now_text, "slot": slot, "files": []}
            ops.append(op)
        else:
            op["time"] = now_text
            if slot is not None:
                op["slot"] = slot
        files = [x for x in op.get("files", [])
                 if isinstance(x, dict) and x.get("source") != fname]
        files.append({
            "source": fname,
            "path": os.path.basename(target),
            "name": os.path.basename(target),
            "sha256": dst_sha,
            "size": os.path.getsize(target),
        })
        op["files"] = files
        _write_backup_manifest(backup_dir, manifest)
        return target

    @property
    def modified(self) -> bool:
        return self._modified

    @property
    def file_size(self) -> int:
        return len(self._data)
