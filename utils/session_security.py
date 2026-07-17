from flask import session


def rotate_session():
    _flashes = session.get("_flashes")
    _user_id = session.get("_user_id")
    _remember = session.get("_remember")
    _fresh = session.get("_fresh")
    session.clear()
    if _flashes is not None:
        session["_flashes"] = _flashes
    if _user_id is not None:
        session["_user_id"] = _user_id
    if _remember is not None:
        session["_remember"] = _remember
    if _fresh is not None:
        session["_fresh"] = _fresh
