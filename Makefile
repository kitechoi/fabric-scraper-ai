VENV = .venv/bin

.PHONY: test dev test-e2e install

# unit + integration 테스트 (빠름, make dev 전에 자동 실행)
test:
	$(VENV)/pytest tests/unit tests/integration

# 테스트 통과 후 Streamlit 시작 (기본 진입점)
dev: test
	$(VENV)/streamlit run ui/app.py

# e2e 테스트 (느림 — 실제 네트워크 + LLM 호출)
test-e2e:
	$(VENV)/pytest tests/e2e -m e2e -v

# 의존성 설치
install:
	python3 -m venv .venv
	$(VENV)/pip install -r requirements.txt
