from datetime import datetime, timedelta, timezone

import aws_longer
import keyring

aws_longer.KEYRING_SERVICE_NAME = "aws_longer_test"


def setup():
    for username in (aws_longer.SESSION_KEYRING_USERNAME, "account_role"):
        try:
            keyring.delete_password(
                service_name=aws_longer.KEYRING_SERVICE_NAME, username=username
            )
        except keyring.errors.PasswordDeleteError:
            pass


def test_cache_in_keyring__change_account_name():
    function = aws_longer.cache_in_keyring(lambda x, **kwargs: x)
    now = datetime.now(timezone.utc)
    expected = {"Expiration": now + timedelta(minutes=2)}

    assert expected == function(expected, account="account", role="role")
    assert expected == function({"Expiration": now}, account="account", role="role")


def test_cache_in_keyring__use_cached_value():
    function = aws_longer.cache_in_keyring(lambda x: x)
    now = datetime.now(timezone.utc)
    expected = {"Expiration": now + timedelta(minutes=2)}

    assert expected == function(expected)
    assert expected == function({"Expiration": now})


def test_cache_in_keyring__dont_use_expired_value():
    function = aws_longer.cache_in_keyring(lambda x: x)
    now = datetime.now(timezone.utc)
    expected = {"Expiration": now + timedelta(minutes=1)}

    assert expected == function(expected)
    assert expected != function({"Expiration": now})
