import inspect

from scripts import run_local_demo as demo


def test_local_demo_uses_only_reserved_synthetic_accounts():
    accounts = {demo.USER_ADMIN, demo.USER_PROPOSER, demo.USER_RUNNER}
    assert len(accounts) == 3
    assert all(account.endswith("@afs.invalid") for account in accounts)


def test_local_demo_source_does_not_pin_a_real_company_email():
    source = inspect.getsource(demo)
    assert "@lsmnm.com" not in source
