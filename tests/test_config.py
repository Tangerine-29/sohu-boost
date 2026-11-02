"""配置读写测试。"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import watcher_config as wc


def test_defaults():
    for k in ('keyword', 'window_days', 'max_exposure', 'boost_workers'):
        assert k in wc.DEFAULTS, f'缺少默认项 {k}'


def test_build_regex():
    re1 = wc.build_regex({'keyword': 'exposure', 'pattern': ''})
    assert re1.search('<exposure:300>')
    assert re1.search('＜exposure：500＞')      # 全角
    assert not re1.search('<promo:300>')

    re2 = wc.build_regex({'keyword': 'promo', 'pattern': ''})
    assert re2.search('<promo:300>')
    assert not re2.search('<exposure:300>')


def test_save_load_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'cfg.json'
        orig = wc.CONFIG_PATH
        try:
            wc.CONFIG_PATH = p
            wc.save({'keyword': 'test', 'window_days': 3, 'max_exposure': 999})
            loaded = wc.load()
            assert loaded['keyword'] == 'test'
            assert loaded['window_days'] == 3
            assert loaded['max_exposure'] == 999
        finally:
            wc.CONFIG_PATH = orig


if __name__ == '__main__':
    test_defaults()
    test_build_regex()
    test_save_load_roundtrip()
    print('✅ 配置测试通过')
