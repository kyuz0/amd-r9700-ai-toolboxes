import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("gguf-vram-estimator.py")
SPEC = importlib.util.spec_from_file_location("gguf_vram_estimator", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def encode_string(value):
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def encode_value(value_type, value):
    formats = {
        4: "<I",
        10: "<Q",
        11: "<q",
        12: "<d",
    }
    if value_type == 8:
        return encode_string(value)
    return struct.pack(formats[value_type], value)


def write_gguf(path, metadata):
    payload = struct.pack("<IIQQ", MODULE.GGUF_MAGIC, 3, 0, len(metadata))
    for key, value_type, value in metadata:
        payload += encode_string(key)
        payload += struct.pack("<I", value_type)
        payload += encode_value(value_type, value)
    path.write_bytes(payload)


class GGUFMetadataReaderTest(unittest.TestCase):
    def read_metadata(self, metadata):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "model.gguf"
            write_gguf(path, metadata)
            return MODULE.GGUFMetadataReader(str(path)).read().metadata

    def test_skips_64_bit_scalar_metadata_without_losing_cursor(self):
        metadata = self.read_metadata([
            ("general.architecture", 8, "qwen35"),
            ("unrelated.uint64", 10, 2**40),
            ("unrelated.int64", 11, -(2**40)),
            ("unrelated.float64", 12, 3.5),
            ("qwen35.block_count", 4, 40),
        ])

        self.assertEqual(metadata["qwen35.block_count"], 40)

    def test_reads_architecture_metadata_that_precedes_architecture_name(self):
        metadata = self.read_metadata([
            ("qwen35.block_count", 4, 40),
            ("general.architecture", 8, "qwen35"),
            ("qwen35.context_length", 4, 262144),
        ])

        self.assertEqual(metadata["general.architecture"], "qwen35")
        self.assertEqual(metadata["qwen35.block_count"], 40)
        self.assertEqual(metadata["qwen35.context_length"], 262144)


if __name__ == "__main__":
    unittest.main()
