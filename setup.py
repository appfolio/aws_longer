import re
from os import path

from setuptools import setup

PACKAGE_NAME = "aws_longer"
HERE = path.abspath(path.dirname(__file__))
with open(path.join(HERE, "README.md"), encoding="utf-8") as fp:
    README = fp.read()
with open(path.join(HERE, PACKAGE_NAME, "__init__.py"), encoding="utf-8") as fp:
    VERSION = re.search('__version__ = "([^"]+)"', fp.read()).group(1)


extras_require = {
    "development": ["pre-commit", "twine", "wheel"],
    "lint": ["black", "flake8"],
    "test": ["pytest"],
}
extras_require["development"] = sorted(set(sum(extras_require.values(), [])))
extras_require["yubikey"] = ["yubikey-manager"]


setup(
    author="Bryce Boe",
    author_email="bbzbryce@gmail.com",
    classifiers=[
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    description="A program to create deterministic zip files.",
    entry_points={"console_scripts": [f"{PACKAGE_NAME} = {PACKAGE_NAME}:main"]},
    extras_require=extras_require,
    install_requires=["boto3", "keyring"],
    keywords="aws assume-role mfa session-token",
    license="Simplified BSD License",
    long_description=README,
    long_description_content_type="text/markdown",
    name=PACKAGE_NAME,
    packages=[PACKAGE_NAME],
    url="https://github.com/appfolio/aws_longer",
    version=VERSION,
)
