# Minimal setup that must be called very early in the app, before any SSL connections are setup

import os
import sys

import certifi


def setup_certs():
    # In a PyInstaller bundled app, resource files are in a temporary folder accessible via sys._MEIPASS.
    # Load the bundled certifi cacert.pem into the environment for SSL
    if getattr(sys, "frozen", False):
        # Set the SSL_CERT_FILE environment variable to use the certifi bundle
        os.environ["SSL_CERT_FILE"] = certifi.where()
