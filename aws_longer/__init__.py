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


__version__ = "0.3.0"
ACCOUNT_MAPPING_FILENAME = os.path.expanduser("~/.aws/accounts")
KEYRING_SERVICE_NAME = "aws_longer"
ROLE_TOKEN_DURATION = 3600
SESSION_TOKEN_DURATION = 129600
SESSION_KEYRING_USERNAME = "__SESSION__"


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
            username = SESSION_KEYRING_USERNAME

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


def get_token(arguments, mfa_token_callback):
    if arguments.command == "role":

        def client_callback():
            token = session_token(mfa_token_callback=mfa_token_callback)
            return boto3_session().client(
                aws_access_key_id=token["AccessKeyId"],
                aws_secret_access_key=token["SecretAccessKey"],
                aws_session_token=token["SessionToken"],
                service_name="sts",
            )

        token = role_token(
            client_callback, account=arguments.account, role=arguments.role
        )
    else:
        token = session_token(mfa_token_callback=mfa_token_callback)
    return token


def handle_cleanup(arguments):
    if arguments.command == "role":
        username = f"{arguments.account}_{arguments.role}"
    else:
        username = SESSION_KEYRING_USERNAME
    try:
        keyring.delete_password(service_name=KEYRING_SERVICE_NAME, username=username)
    except keyring.errors.PasswordDeleteError:
        pass


@cache_in_keyring
def role_token(client_callback, *, account, role):
    response = client_callback().assume_role(
        DurationSeconds=ROLE_TOKEN_DURATION,
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
        "-m",
        "--mfa-token",
        help="When an MFA token is required, pass in this value instead of prompting for it.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--yubikey",
        help="When an MFA token is required, obtain it from the attached yubikey using the provided name.",
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
    if arguments.mfa_token and arguments.yubikey:
        parser.error("Cannot provide both --mfa-token and --yubikey")
        return 1

    if arguments.cleanup:
        handle_cleanup(arguments)
        return 0

    def mfa_token_callback():
        if arguments.mfa_token:
            return arguments.mfa_token
        if arguments.yubikey is None:
            return None
        try:
            import ykman
        except ModuleNotFoundError:
            print(
                "Please ensure ykman is installed. Try: `pip install aws_longer[yubikey]`"
            )
            return None
        import subprocess

        process = subprocess.run(
            ["ykman", "oath", "code", "--single", arguments.yubikey],
            stdout=subprocess.PIPE,
        )
        if process.returncode != 0:
            raise GracefulExit
        return process.stdout.strip().decode("utf-8")

    clean_environment()

    try:
        token = get_token(arguments, mfa_token_callback)
    except GracefulExit:
        print("Leaving aws_longer.")
        token = None

    if token:
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
    ), "How is it possible that there are more than one MFA device?"
    return devices[0]["SerialNumber"]


@cache_in_keyring
def session_token(mfa_token_callback):
    client = boto3_session().client("sts")
    mfa_serial = mfa_serial_number()
    mfa_token = mfa_token_callback()
    response = None
    while response is None:
        try:
            mfa_token = mfa_token or input("MFA Token: ")
        except EOFError:
            raise GracefulExit
        except KeyboardInterrupt:
            sys.exit(1)
        try:
            response = client.get_session_token(
                DurationSeconds=SESSION_TOKEN_DURATION,
                SerialNumber=mfa_serial,
                TokenCode=mfa_token,
            )
        except (
            botocore.exceptions.ClientError,
            botocore.exceptions.ParamValidationError,
        ) as exception:
            print(exception)
            mfa_token = None
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


class GracefulExit(Exception):
    pass
