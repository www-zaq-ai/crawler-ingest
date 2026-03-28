"""Unit tests for image_dedup.py"""

import io
import pytest
from pathlib import Path
from PIL import Image

from image_dedup import (
    get_image_hash,
    are_images_similar,
    deduplicate_images,
    deduplicate_image_files,
    save_duplicate_mapping,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pattern_image(pattern: str = "left-white") -> Image.Image:
    """
    Return a 32x32 image with a distinct spatial pattern so average_hash
    produces a meaningful (non-zero) hash.

    Patterns:
      "left-white"  — left half white, right half black
      "left-black"  — left half black, right half white
      "top-white"   — top half white, bottom half black
      "checkerboard"— alternating 4x4 black/white squares
    """
    img = Image.new("RGB", (32, 32), (0, 0, 0))
    pixels = img.load()
    if pattern == "left-white":
        for x in range(16):
            for y in range(32):
                pixels[x, y] = (255, 255, 255)
    elif pattern == "left-black":
        for x in range(16, 32):
            for y in range(32):
                pixels[x, y] = (255, 255, 255)
    elif pattern == "top-white":
        for x in range(32):
            for y in range(16):
                pixels[x, y] = (255, 255, 255)
    elif pattern == "checkerboard":
        for x in range(32):
            for y in range(32):
                if (x // 4 + y // 4) % 2 == 0:
                    pixels[x, y] = (255, 255, 255)
    return img


def _image_bytes(pattern: str = "left-white") -> bytes:
    buf = io.BytesIO()
    _pattern_image(pattern).save(buf, format="PNG")
    return buf.getvalue()


def _save_image(path: Path, pattern: str = "left-white"):
    _pattern_image(pattern).save(path)


# ---------------------------------------------------------------------------
# get_image_hash
# ---------------------------------------------------------------------------

class TestGetImageHash:
    def test_accepts_bytes(self):
        assert get_image_hash(_image_bytes()) is not None

    def test_accepts_pil_image(self):
        assert get_image_hash(_pattern_image()) is not None

    def test_identical_images_same_hash(self):
        assert get_image_hash(_image_bytes()) == get_image_hash(_image_bytes())

    def test_different_images_different_hash(self):
        h1 = get_image_hash(_image_bytes("left-white"))
        h2 = get_image_hash(_image_bytes("top-white"))
        assert h1 != h2


# ---------------------------------------------------------------------------
# are_images_similar
# ---------------------------------------------------------------------------

class TestAreImagesSimilar:
    def test_identical_images_are_similar(self):
        img = _image_bytes("left-white")
        assert are_images_similar(img, img)

    def test_very_different_images_not_similar(self):
        a = _image_bytes("left-white")
        b = _image_bytes("top-white")
        assert not are_images_similar(a, b, threshold=5)

    def test_threshold_zero_accepts_exact_match(self):
        img = _image_bytes("left-white")
        assert are_images_similar(img, img, threshold=0)

    def test_high_threshold_accepts_different_images(self):
        a = _image_bytes("left-white")
        b = _image_bytes("top-white")
        # threshold=64 is the maximum Hamming distance for hash_size=8
        assert are_images_similar(a, b, threshold=64)


# ---------------------------------------------------------------------------
# deduplicate_images
# ---------------------------------------------------------------------------

class TestDeduplicateImages:
    def test_empty_list_returns_empty(self):
        unique, dupes = deduplicate_images([])
        assert unique == []
        assert dupes == []

    def test_single_image_no_duplicates(self):
        img = _image_bytes()
        unique, dupes = deduplicate_images([img])
        assert len(unique) == 1
        assert dupes == []

    def test_identical_images_deduped(self):
        img = _image_bytes()
        unique, dupes = deduplicate_images([img, img, img])
        assert len(unique) == 1
        assert dupes == [1, 2]

    def test_distinct_images_all_kept(self):
        imgs = [_image_bytes(p) for p in ("left-white", "top-white", "checkerboard")]
        unique, dupes = deduplicate_images(imgs)
        assert len(unique) == 3
        assert dupes == []

    def test_duplicate_index_reflects_position(self):
        a = _image_bytes("left-white")
        b = _image_bytes("top-white")
        _, dupes = deduplicate_images([a, b, a])
        assert 2 in dupes


# ---------------------------------------------------------------------------
# deduplicate_image_files
# ---------------------------------------------------------------------------

class TestDeduplicateImageFiles:
    def test_empty_list_returns_empty(self):
        unique, mapping = deduplicate_image_files([])
        assert unique == []
        assert mapping == {}

    def test_unique_files_all_returned(self, tmp_path):
        paths = []
        for i, pattern in enumerate(("left-white", "top-white", "checkerboard")):
            p = tmp_path / f"img{i}.png"
            _save_image(p, pattern)
            paths.append(p)
        unique, mapping = deduplicate_image_files(paths)
        assert len(unique) == 3
        assert mapping == {}

    def test_duplicate_files_mapped_to_original(self, tmp_path):
        orig = tmp_path / "orig.png"
        dup = tmp_path / "dup.png"
        _save_image(orig, "left-white")
        _save_image(dup, "left-white")
        unique, mapping = deduplicate_image_files([orig, dup])
        assert len(unique) == 1
        assert str(dup) in mapping
        assert mapping[str(dup)] == str(orig)

    def test_first_occurrence_is_kept_as_original(self, tmp_path):
        first = tmp_path / "first.png"
        second = tmp_path / "second.png"
        _save_image(first, "left-white")
        _save_image(second, "left-white")
        unique, mapping = deduplicate_image_files([first, second])
        assert first in unique


# ---------------------------------------------------------------------------
# save_duplicate_mapping
# ---------------------------------------------------------------------------

class TestSaveDuplicateMapping:
    def test_creates_file(self, tmp_path):
        out = tmp_path / "mapping.txt"
        save_duplicate_mapping({"dup.png": "orig.png"}, str(out))
        assert out.exists()

    def test_file_contains_mapping_entries(self, tmp_path):
        out = tmp_path / "mapping.txt"
        save_duplicate_mapping({"dup.png": "orig.png"}, str(out))
        content = out.read_text()
        assert "dup.png -> orig.png" in content

    def test_empty_mapping_writes_only_header(self, tmp_path):
        out = tmp_path / "mapping.txt"
        save_duplicate_mapping({}, str(out))
        content = out.read_text()
        assert "Total duplicates: 0" in content

    def test_creates_parent_directories(self, tmp_path):
        out = tmp_path / "subdir" / "deep" / "mapping.txt"
        save_duplicate_mapping({"a.png": "b.png"}, str(out))
        assert out.exists()
