"""存档读写自检：造一份假存档 → 读写 → 回读比对。

不依赖游戏本体，也不需要显示器：
    python selftest.py

覆盖：
  1. 合法尺寸的 GameData / SlotData 能正常载入
  2. 金币读写
  3. 小恢复药（item_id = 0）不会被当成空槽
  4. 武器可以写入并回读
  5. 芯片增删与空槽判定
  6. 保存后文件大小不变（不静默扩容）、无残留 .tmp
  7. 过小 / 被截断的文件会被拒绝载入
"""

import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import constants as K
from chip_data import REGISTRY as CHIPS
from item_data import get_item_name, get_category, is_weapon, ITEM_NAMES
from save_io import SaveError, SaveFile

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def make_saves(tmp: str) -> tuple[str, str]:
    """造一份 400KB GameData + 231KB SlotData 的空存档"""
    gd = os.path.join(tmp, "GameData.dat")
    sd = os.path.join(tmp, "SlotData_0.dat")

    g = bytearray(400_000)
    s = bytearray(231_000)
    struct.pack_into("<I", g, K.OFFSET_MONEY, 5000)
    struct.pack_into("<I", s, K.OFFSET_MONEY, 5000)
    for i in range(K.SLOT_MAX_ITEMS):
        off = K.OFFSET_ITEMS_START + i * K.ITEM_RECORD_SIZE
        struct.pack_into("<H", g, off, K.ITEM_EMPTY_ID)
        struct.pack_into("<H", s, off, K.ITEM_EMPTY_ID)
    # 芯片区：全 0xFF = 空
    s[K.OFFSET_CHIPS_START:K.OFFSET_CHIPS_START + K.MAX_CHIPS * K.CHIP_RECORD_SIZE] = (
        b"\xff" * (K.MAX_CHIPS * K.CHIP_RECORD_SIZE)
    )

    with open(gd, "wb") as f:
        f.write(g)
    with open(sd, "wb") as f:
        f.write(s)
    return gd, sd


def main() -> int:
    print("数据表")
    check("道具 + 武器共 260 条", len(ITEM_NAMES) == 260, f"实际 {len(ITEM_NAMES)}")
    check("武器 39 把", sum(1 for i in ITEM_NAMES if is_weapon(i)) == 39)
    check("小恢复药 = 0x0000", get_item_name(0) == "小恢复药")
    check("白之契约 = 0x042E", get_item_name(0x042E) == "白之契约")
    check("武器分类正确", get_category(0x042E) == "武器·小型剑", get_category(0x042E))

    tmp = tempfile.mkdtemp(prefix="nier-selftest-")
    gd, sd = make_saves(tmp)

    print("\n载入")
    g, s = SaveFile(gd), SaveFile(sd)
    check("GameData 载入", g.get_money() == 5000)
    check("SlotData 载入", s.get_money() == 5000)
    check("SlotData 道具只有 512 条", len(s.get_items()) == K.SLOT_MAX_ITEMS, str(len(s.get_items())))

    print("\n写入")
    s.add_or_update_item(0x0000, 7, limit=K.SLOT_MAX_ITEMS)      # 小恢复药
    s.add_or_update_item(0x042E, 1, limit=K.SLOT_MAX_ITEMS)      # 白之契约
    owned = dict(s.get_owned_items())
    check("小恢复药写入（id=0 不被当空槽）", owned.get(0) == 7, str(owned))
    check("武器写入", owned.get(0x042E) == 1)
    check("武器名称", get_item_name(0x042E) == "白之契约")

    chip = CHIPS.to_bytes("HP最大值UP +3")
    check("芯片写入", s.add_chip(chip))
    check("芯片等级回读", s.get_installed_chips()[0]["level"] == 3)
    s.remove_chip(0)
    check("芯片删除后判空", s.get_chips()[0]["empty"])
    check("删除后无已装芯片", not s.get_installed_chips())

    print("\n保存")
    before = (os.path.getsize(gd), os.path.getsize(sd))
    g.sync_money_items_from(s)
    g.set_money(8888)
    s.set_money(8888)
    g.save()
    s.save()
    after = (os.path.getsize(gd), os.path.getsize(sd))
    check("文件大小不变（不扩容）", before == after, f"{before} -> {after}")
    check("无残留 .tmp", not [f for f in os.listdir(tmp) if f.endswith(".tmp")])

    g2, s2 = SaveFile(gd), SaveFile(sd)
    check("金币回读", g2.get_money() == 8888 and s2.get_money() == 8888)
    check("道具回读", dict(s2.get_owned_items()).get(0x042E) == 1)
    check("GameData 与 SlotData 道具区一致",
          g2.get_items(K.SLOT_MAX_ITEMS) == s2.get_items(K.SLOT_MAX_ITEMS))

    print("\n非法文件")
    bad = os.path.join(tmp, "GameData_truncated.dat")
    with open(bad, "wb") as f:
        f.write(b"\x00" * 1000)
    try:
        SaveFile(bad)
        check("截断文件被拒绝", False)
    except SaveError:
        check("截断文件被拒绝", True)

    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
