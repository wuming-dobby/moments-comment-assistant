"""v0.3 模块③：截图压缩——长边≤800、JPEG q75（真图打桩，PIL 验证）。"""
import base64
import io

from PIL import Image

import vision


def _png_bytes(size):
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, "PNG")
    return buf.getvalue()


def test_large_image_scaled_to_800(tmp_path):
    img = tmp_path / "big.png"
    img.write_bytes(_png_bytes((1600, 900)))
    url = vision.image_to_data_url(str(img))

    assert url.startswith("data:image/jpeg;base64,")
    raw = base64.b64decode(url.split(",", 1)[1])
    out = Image.open(io.BytesIO(raw))
    assert out.format == "JPEG"
    assert max(out.size) == 800, "长边应压到 800，实际 %r" % (out.size,)


def test_small_image_kept(tmp_path):
    img = tmp_path / "small.png"
    img.write_bytes(_png_bytes((400, 300)))
    url = vision.image_to_data_url(str(img))
    raw = base64.b64decode(url.split(",", 1)[1])
    out = Image.open(io.BytesIO(raw))
    assert max(out.size) == 400, "小图不该放大"


def test_local_file_untouched(tmp_path):
    img = tmp_path / "keep.png"
    png = _png_bytes((1200, 600))
    img.write_bytes(png)
    vision.image_to_data_url(str(img))
    assert img.read_bytes() == png, "本地保存的 PNG 截图不能被改动"
