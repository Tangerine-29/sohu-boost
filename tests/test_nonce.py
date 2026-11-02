"""s-nonce 生成测试。"""

import base64
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from boost_protocol import gen_nonce


def test_nonce_format():
    n = gen_nonce()
    assert isinstance(n, str)
    assert '=' not in n, '末尾不应有 ='
    raw = base64.urlsafe_b64decode(n + '=' * (-len(n) % 4))
    assert len(raw) == 48, '应是 8 字节时间戳 + 40 字节随机'


def test_nonce_timestamp():
    before = int(time.time() * 1000)
    n = gen_nonce()
    after = int(time.time() * 1000)
    raw = base64.urlsafe_b64decode(n + '=' * (-len(n) % 4))
    ts = struct.unpack('>Q', raw[:8])[0]
    assert before - 1000 <= ts <= after + 1000, '时间戳应接近当前时间'


def test_nonce_unique():
    a = gen_nonce()
    b = gen_nonce()
    assert a != b, '每次必须不同'


if __name__ == '__main__':
    test_nonce_format()
    test_nonce_timestamp()
    test_nonce_unique()
    print('✅ nonce 测试通过')
