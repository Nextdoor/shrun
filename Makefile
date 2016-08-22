SHRUN=shrun

.PHONY: test

test:
	py.test $(TOXARGS)
	$(MAKE) smoke_test

smoke_test:
	@echo "Running smoke test"
	@echo "This should pass:"
	$(SHRUN) samples/pass.yml
	@echo "This should fail:"
	! $(SHRUN) samples/fail.yml
	@echo "Success!"

init:
	-flake8 --install-hook  # allow this line to fail
	pip install -r requirements.txt
	pip install -e .
