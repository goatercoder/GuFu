from fastapi import Request

from gufu.state import AppState


def get_state(request: Request) -> AppState:
    return request.app.state.gufu
