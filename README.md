# aws_longer

`aws_longer` is a tool to replace
[assume-role](https://github.com/coinbase/assume-role) with a few significant
benefits:

1) MFA tokens need only be entered once every 36 hours.
2) Sessions can be shared across terminals, and persist across reboots.

Both of the above are accomplished by storing the session credentials, and
assumed credentials in the user's keychain.

## Installation

Install this package via:

```sh
pip install aws_longer
```

If you'd like to use this package with your yubikey please run:

```sh
pip install aws_longer[yubikey]  # Escape the brackets in zsh
```

## Assuming a Role

```sh
aws_longer role ROLENAME AWS_ACCOUNT
```

The above will open a new shell setting the appropriate `AWS_` environment
variables. If this is the first time you are running this command, or it has
been 36 hours since you last input your MFA token, then you will be prompted to
input your MFA token.

`AWS_ACCOUNT` can either be an AWS account ID, or an alias to an AWS account
ID.

If you'd like to prevent opening a new shell, you can instead run, but be
careful because if there are any errors, the result will terminate your
shell-program:

```sh
exec aws_longer role ROLENAME AWS_ACCOUNT
```

## Using the Temporary Session

Rather than assuming a specific role, one can directly utilize the 36-hour
temporary session via:

```sh
aws_longer
```

Using this temporary session is beneficial if, for example, you require MFA to
assume roles, and you'd like to be able to run `terraform apply` with a
provider that assumes a specific role.


## AWS Account ID Alias

AWS account ID aliases can be defined in `~/.aws/accounts`, which is a JSON
file of the following format:

```json
{
  "default": "123456789012",
  "staging": "123456789012",
  "production": "123456789012"
}
```

This aliasing format is the same as was used in
[assume-role](https://github.com/coinbase/assume-role#account-aliasing) in
order to ease transitioning.

## Avoid token prompting

If you happen to use a program to generate your MFA token, you might prefer to
pass the token directly as part of the command invocation instead of via a
prompt to STDIN. Do that via:

```sh
aws_longer --mfa-token TOKEN role ROLENAME AWS_ACCOUNT
```

In said cases, the MFA token will only be used if it's necessary to do so.

### Yubikeys

If you are using a Yubikey in TOTP mode, you can use it via:

```sh
aws_longer --yubikey NAME role ROLENAME AWS_ACCOUNT
```

To discover the name on your yubikey, you can list all names via:

```sh
ykman oath list
```
