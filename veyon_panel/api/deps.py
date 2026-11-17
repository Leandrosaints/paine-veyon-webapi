from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from veyon_panel.db.session import get_db
from veyon_panel.models.resources import Computer, Environment


def require_environment(environment_id: int, db: Session = Depends(get_db)) -> Environment:
    item = db.get(Environment, environment_id)
    if item is None:
        raise HTTPException(404, "Ambiente não encontrado.")
    return item


def require_computer(computer_id: int, db: Session = Depends(get_db)) -> Computer:
    item = db.get(Computer, computer_id)
    if item is None:
        raise HTTPException(404, "Computador não encontrado.")
    return item
