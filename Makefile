# 常用命令
.PHONY: help check test clean deploy lint scan

PY ?= python3

help:            ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

check:           ## 环境自检（需要先配置好 session_sample.json）
	@bash check.sh

test:            ## 跑全部测试（语法 + 单元测试）
	@$(PY) -m py_compile *.py && echo "✅ 语法通过"
	@$(PY) -c "import sign, payload, watcher_config, token_stats" && echo "✅ 导入通过"
	@echo ""
	@$(PY) tests/run_all.py

scan:            ## 扫描敏感信息（提交前必跑）
	@if grep -rnE 'sk-[a-zA-Z0-9]{20,}|eyJleHAiOjE[0-9]{8}' \
		--include='*.py' --include='*.json' --include='*.md' . \
		| grep -v 'examples/' | grep -v 'docs/SESSION.md' ; then \
		echo "❌ 发现疑似凭证"; exit 1; \
	else echo "✅ 无敏感信息"; fi

lint: test scan  ## test + scan

deploy:          ## 部署到当前目录（宝塔/服务器）
	@bash install.sh

clean:           ## 清理运行时数据（不会删凭证）
	@rm -rf __pycache__ *.pyc
	@rm -f watcher_state.json token_stats.json
	@echo "✅ 已清理（session_*.json 和 watcher_config.json 保留）"

clean-all:       ## 清理全部（含凭证，慎用）
	@rm -rf __pycache__ *.pyc
	@rm -f watcher_state.json token_stats.json *.log
	@echo "⚠️  已清理运行时数据，凭证文件仍在（手动删）"
