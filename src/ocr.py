"""Windows 自带 OCR 封装（winsdk → Windows.Media.Ocr）：本地识别 PNG 窄带，不联网。

异步链：InMemoryRandomAccessStream → BitmapDecoder → SoftwareBitmap → OcrEngine → recognize_async。
import 失败 / 无语言包 / 识别异常统一抛 OcrUnavailable，由调用方降级。
"""
import asyncio

MOMENTS_KEYWORD = "朋友圈"


def moments_hit(text):
    """OCR 常把汉字逐字加空格输出（真机实测「朋 友 圈」），匹配前去空白。"""
    return MOMENTS_KEYWORD in "".join(text.split())


class OcrUnavailable(RuntimeError):
    """winsdk 未装 / 无 OCR 语言包 / 识别异常。"""


try:
    import winsdk.windows.graphics.imaging as _wimaging
    import winsdk.windows.media.ocr as _wocr
    import winsdk.windows.storage.streams as _wstreams
    _WINSDK_OK = True
except Exception:
    _wimaging = _wocr = _wstreams = None
    _WINSDK_OK = False


async def _recognize(png_bytes):
    if not _WINSDK_OK:
        raise OcrUnavailable("winsdk 不可用（未安装或加载失败）")
    stream = _wstreams.InMemoryRandomAccessStream()
    writer = _wstreams.DataWriter(stream)
    writer.write_bytes(png_bytes)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)
    decoder = await _wimaging.BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = _wocr.OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise OcrUnavailable("无可用 OCR 语言（系统未装中文语言包）")
    result = await engine.recognize_async(bitmap)
    return result.text


def ocr_text(png_bytes):
    """PNG 字节 → 识别文本。失败抛 OcrUnavailable。"""
    try:
        return asyncio.run(_recognize(png_bytes))
    except OcrUnavailable:
        raise
    except Exception as exc:
        raise OcrUnavailable("OCR 识别失败：%s" % exc) from exc
