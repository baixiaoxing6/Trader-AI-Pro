COMPOSE := docker compose
SERVICE := freqtrade-signal
CONFIG := /freqtrade/user_data/configs/config.signal.json
SMOKE_CONFIG := /freqtrade/user_data/configs/config.backtest-smoke.json
STRATEGY := TraderAIProSignalStrategy
MODEL := LightGBMRegressor
SMOKE_DATA_START ?= 2021-07-01
SMOKE_DATA_END ?= 2021-07-08
SMOKE_TIMERANGE ?= 20210705-20210707

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
	$(COMPOSE) run --rm --no-deps --entrypoint python $(SERVICE) \
		/freqtrade/scripts/prepare_bybit_public_data.py \
		--symbol SOLUSDT \
		--pair SOL/USDT:USDT \
		--start $(SMOKE_DATA_START) \
		--end $(SMOKE_DATA_END)
	$(COMPOSE) run --rm --no-deps --entrypoint python $(SERVICE) \
		/freqtrade/scripts/run_offline_backtest.py \
		--config $(CONFIG) \
		--config $(SMOKE_CONFIG) \
		--strategy $(STRATEGY) \
		--freqaimodel $(MODEL) \
		--timerange $(SMOKE_TIMERANGE)
	python3 scripts/validate_backtest.py user_data/backtest_results \
		--strategy $(STRATEGY)
