import argparse
import base64
import json
import os
import pickle
import sys
from datetime import datetime, timedelta, timezone
from functools import wraps

import boto3
import botocore
import keyring


__version__ = "0.1.1"
ACCOUNT_MAPPING_FILENAME = os.path.expanduser("~/.aws/accounts")
KEYRING_SERVICE_NAME = "aws_longer"


def _boto3_session_closure():
    session = None

    def closure():
        nonlocal session
        if session is None:
            session = boto3.session.Session()
        return session

    return closure


boto3_session = _boto3_session_closure()


def cache_in_keyring(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if kwargs.get("account"):
            username = f"{kwargs['account']}_{kwargs['role']}"
        else:
            username = ""

        serialized = keyring.get_password(
            service_name=KEYRING_SERVICE_NAME, username=username
        )
        if serialized:
            token = pickle.loads(base64.b64decode(serialized))
            check_time = datetime.now(timezone.utc) + timedelta(minutes=1)
            if check_time > token["Expiration"]:
                serialized = None
        if serialized is None:
            token = function(*args, **kwargs)
            serialized = base64.b64encode(
                pickle.dumps(token, protocol=pickle.HIGHEST_PROTOCOL)
            ).decode("utf-8")
            keyring.set_password(
                password=serialized,
                service_name=KEYRING_SERVICE_NAME,
                username=username,
            )

        return token

    return wrapper


def clean_environment():
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        if name in os.environ:
            del os.environ[name]


def discover_shell():
    return os.environ.get("SHELL", "/bin/sh")


def handle_cleanup(arguments):
    if arguments.command == "role":
        username = f"{arguments.account}_{arguments.role}"
    else:
        username = ""
    try:
        keyring.delete_password(service_name=KEYRING_SERVICE_NAME, username=username)
    except keyring.errors.PasswordDeleteError:
        pass


@cache_in_keyring
def role_token(client, *, account, role):
    response = client.assume_role(
        DurationSeconds=3600,
        ExternalId=account,
        RoleArn=f"arn:aws:iam::{account}:role/{role}",
        RoleSessionName=os.environ.get("USER", "__"),
    )
    return response["Credentials"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cleanup", action="store_true", help="Delete cached token from keychain."
    )
    parser.add_argument(
        "-s",
        "--shell",
        help="The shell to exec (default: %(default)s).",
        default=discover_shell(),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command")
    role_parser = subparsers.add_parser("role")
    role_parser.add_argument("role")
    role_parser.add_argument(
        "account",
        help=f"Either an AWS account number, or the name of a key that maps to an account number in {ACCOUNT_MAPPING_FILENAME}.",
        type=validate_account,
    )

    arguments = parser.parse_args()
    if arguments.cleanup:
        handle_cleanup(arguments)
        return 0

    clean_environment()
    token = session_token()
    if arguments.command == "role":
        client = boto3_session().client(
            aws_access_key_id=token["AccessKeyId"],
            aws_secret_access_key=token["SecretAccessKey"],
            aws_session_token=token["SessionToken"],
            service_name="sts",
        )
        token = role_token(client, account=arguments.account, role=arguments.role)
    set_environment(token)

    os.execlp(arguments.shell, arguments.shell)


def mfa_serial_number():
    client = boto3_session().client("iam")
    response = client.list_mfa_devices()
    devices = response["MFADevices"]
    if not devices:
        sys.stderr.write(f"No MFA devices found.\n")
        sys.exit(1)
    assert (
        len(devices) == 1
    ), "How is it possible that there is more than one MFA device?"
    return devices[0]["SerialNumber"]


@cache_in_keyring
def session_token():
    client = boto3_session().client("sts")
    response = None
    while response is None:
        mfa_serial = mfa_serial_number()
        mfa_token = input("MFA Token: ")
        try:
            response = client.get_session_token(
                DurationSeconds=129600, SerialNumber=mfa_serial, TokenCode=mfa_token,
            )
        except (
            botocore.exceptions.ClientError,
            botocore.exceptions.ParamValidationError,
        ) as exception:
            print(exception)
    return response["Credentials"]


def set_environment(token):
    os.environ["AWS_ACCESS_KEY_ID"] = token["AccessKeyId"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = token["SecretAccessKey"]
    os.environ["AWS_SESSION_TOKEN"] = token["SessionToken"]


def validate_account(account):
    if account.isnumeric():
        return account

    try:
        with open(ACCOUNT_MAPPING_FILENAME) as fp:
            accounts = json.load(fp)
    except FileNotFoundError as exception:
        raise argparse.ArgumentTypeError(exception)
    except json.JSONDecodeError:
        raise argparse.ArgumentTypeError(
            f"{fp.name} does not appear to be a valid JSON file"
        )

    if not isinstance(accounts, dict):
        raise argparse.ArgumentTypeError(
            f"{ACCOUNT_MAPPING_FILENAME} is not in the correct format"
        )

    if account not in accounts:
        raise argparse.ArgumentTypeError(
            f"{account} is not found in {ACCOUNT_MAPPING_FILENAME}"
        )

    return accounts[account]
