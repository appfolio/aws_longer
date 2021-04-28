# Change Log

## Unreleased

__Changed__

* Use IAM `UserName` for `RoleSession` name instead of the OS username.

## 0.3.0 (2020/04/17)

__Added__

* Support yubikeys via the `--yubikey NAME` argument.

__Fixed__

* `--cleanup` works again for clearing the temporary credentials (non-role
  based one)

## 0.2.1 (2020/04/03)

__Fixed__

* Only prompt for session MFA when it actually is needed.
* Avoid pulling in a random role token as the session token when the session
  token expires.

## 0.2.0 (2020/03/06)

__Added__

* Support MFA input via `--mfa-token` command line option.

## 0.1.2 (2020/03/06)

__Fixed__

* Declare boto3 as a dependency

## 0.1.1 (2020/03/06)

__Fixed__

* Declare keyring as a dependency

## 0.1.0 (2020/03/06)

Initial version.
