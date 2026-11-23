import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# pytest 收集阶段就会 import 所有测试模块；任何模块顶层创建 QWidget
# 都必须晚于 QApplication，否则 qFatal abort（0xC0000409）。全局建一次。
from PyQt5 import QtWidgets  # noqa: E402

_APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
