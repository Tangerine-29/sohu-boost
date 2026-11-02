"""签名算法测试（不依赖网络）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sign import sign


def test_sign_deterministic():
    """同样的参数必须得到同样的签名。"""
    params = {'appid': '330000', 'feed_id': '123', 'flyer': '1000'}
    headers = {'S-CID': '01x', 'S-PID': '1', 'S-PPID': 'a@b.com',
               'S-VS': '6.24.1', 's-nonce': 'abc'}
    a = sign(params, headers)
    b = sign(params, headers)
    assert a == b, '签名必须稳定'
    assert len(a) == 32, '签名应为 32 位 hex'


def test_sign_order_independent():
    """参数顺序不影响结果（内部会排序）。"""
    h = {'S-CID': '01x', 'S-PID': '1', 'S-PPID': 'a@b.com', 'S-VS': '6.24.1', 's-nonce': 'abc'}
    a = sign({'a': '1', 'b': '2'}, h)
    b = sign({'b': '2', 'a': '1'}, h)
    assert a == b


def test_sign_changes_with_value():
    h = {'S-CID': '01x', 'S-PID': '1', 'S-PPID': 'a@b.com', 'S-VS': '6.24.1', 's-nonce': 'abc'}
    a = sign({'a': '1'}, h)
    b = sign({'a': '2'}, h)
    assert a != b, '值变了签名必须变'


if __name__ == '__main__':
    test_sign_deterministic()
    test_sign_order_independent()
    test_sign_changes_with_value()
    print('✅ 签名测试通过')
