import io
import base64
import tempfile
from PIL import Image
from vlm_inspector import prepare_image_for_vlm


def test_prepare_image_for_vlm_large_resize():
    """Ảnh lớn (> 1600px) được tự động co lại với max_dim <= 1600px và kích thước chia hết cho 28."""
    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        Image.new("RGB", (3200, 2400), color="white").save(tmp.name)
        b64 = prepare_image_for_vlm(tmp.name, max_dim=1600)
        decoded = base64.b64decode(b64)
        result = Image.open(io.BytesIO(decoded))

        w, h = result.size
        assert max(w, h) <= 1600
        assert w % 28 == 0
        assert h % 28 == 0


def test_prepare_image_for_vlm_small_dimensions():
    """Ảnh nhỏ (< 1600px) được giữ nguyên tỷ lệ và bo tròn về bội số của 28."""
    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        Image.new("RGB", (800, 600), color="white").save(tmp.name)
        b64 = prepare_image_for_vlm(tmp.name, max_dim=1600)
        decoded = base64.b64decode(b64)
        result = Image.open(io.BytesIO(decoded))

        w, h = result.size
        assert max(w, h) <= 1600
        assert w % 28 == 0
        assert h % 28 == 0
