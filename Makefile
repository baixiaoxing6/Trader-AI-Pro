COMPOSE := docker compose
SERVICE := freqtrade-signal
CONFIG := /freqtrade/user_data/configs/config.signal.json
SMOKE_CONFIG := /freqtrade/user_data/configs/config.backtest-smoke.json
STRATEGY := TraderAIProSignalStrategy
MODEL := LightGBMRegressor
SMOKE_DATA_TIMERANGE ?= 20260720-20260815
SMOKE_TIMERANGE ?= 20260801-20260808

.PHONY: validate pull up logs down download-data backtest smoke-backtest

validate:
	python3 scripts/validate.py
	python3 -m unittest discover -s tests -v
	$(COMPOSE) config --quiet

pull:
	$(COMPOSE) pull

up: validate
	$(COMPOSE) up -d

logs:
	$(COMPOSE) logs -f --tail=200 $(SERVICE)

down:
	$(COMPOSE) down

download-data:
	$(COMPOSE) run --rm $(SERVICE) download-data \
		--config $(CONFIG) \
		--timeframes 5m 15m 1h \
		--days 90

backtest:
	@test -n "$(TIMERANGE)" || (echo "Usage: make backtest TIMERANGE=YYYYMMDD-YYYYMMDD" && exit 2)
	$(COMPOSE) run --rm $(SERVICE) backtesting \
		--config $(CONFIG) \
		--strategy $(STRATEGY) \
		--freqaimodel $(MODEL) \
		--timerange $(TIMERANGE)

smoke-backtest: validate pull
	$(COMPOSE) run --rm --no-deps $(SERVICE) download-data \
		--config $(CONFIG) \
		--config $(SMOKE_CONFIG) \
		--timeframes 5m 15m \
		--timerange $(SMOKE_DATA_TIMERANGE)
	$(COMPOSE) run --rm --no-deps $(SERVICE) backtesting \
		--config $(CONFIG) \
		--config $(SMOKE_CONFIG) \
		--strategy $(STRATEGY) \
		--freqaimodel $(MODEL) \
		--timerange $(SMOKE_TIMERANGE) \
		--export trades \
		--cache none
	python3 scripts/validate_backtest.py user_data/backtest_results \
		--strategy $(STRATEGY)
