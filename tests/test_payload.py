"""埋点编解码测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import payload as P


def test_frame_message():
    raw = b'\x08\x01'
    framed = P.frame_message(raw)
    assert framed != raw, '应加上长度前缀'
    assert framed.endswith(raw), '原始内容在末尾'


def test_build_feed_detail():
    msg = P.build_feed_detail(
        feed_id='123456',
        public_meta={'deviceId': 'x', 'userId': '1'},
    )
    assert isinstance(msg, bytes)
    assert len(msg) > 0


if __name__ == '__main__':
    test_frame_message()
    test_build_feed_detail()
    print('✅ payload 测试通过')
