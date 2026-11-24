"""Deployment switches for the internal request modules."""

import os

from fastapi import HTTPException

REQUEST_FLAGS = {'cr': 'CHANGE_REQUEST_ENABLED', 'sr': 'SERVICE_REQUEST_ENABLED'}


def request_enabled(kind):
    return os.environ.get(REQUEST_FLAGS[kind], 'true').strip().lower() == 'true'


def require_request(kind):
    if not request_enabled(kind):
        raise HTTPException(404, 'Request module is disabled')
