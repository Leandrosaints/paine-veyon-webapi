from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from veyon_panel.core.config import VEYON_API_URL
from veyon_panel.db.session import get_db
from veyon_panel.models.resources import Computer, Environment
from veyon_panel.schemas.resources import (
    ComputerCreate, ComputerRead, ComputerUpdate,
    EnvironmentCreate, EnvironmentRead, EnvironmentUpdate,
)

router = APIRouter(tags=["Ambientes e computadores"])


@router.get("/config")
def config():
    return {"base_url": VEYON_API_URL}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    return {"ok": True, "service": "veyon-control-panel", "storage": "sqlite"}


@router.get("/environments", response_model=list[EnvironmentRead])
def list_environments(db: Session = Depends(get_db)):
    return db.scalars(select(Environment).order_by(Environment.sort_order, Environment.name)).all()


@router.post("/environments", response_model=EnvironmentRead, status_code=201)
def create_environment(body: EnvironmentCreate, db: Session = Depends(get_db)):
    item = Environment(**body.dict())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Já existe um ambiente com esse nome.") from exc
    db.refresh(item)
    return item


@router.patch("/environments/{environment_id}", response_model=EnvironmentRead)
def update_environment(environment_id: int, body: EnvironmentUpdate, db: Session = Depends(get_db)):
    item = db.get(Environment, environment_id)
    if item is None:
        raise HTTPException(404, "Ambiente não encontrado.")
    for key, value in body.dict(exclude_unset=True).items():
        setattr(item, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Já existe um ambiente com esse nome.") from exc
    db.refresh(item)
    return item


@router.delete("/environments/{environment_id}", status_code=204)
def delete_environment(environment_id: int, db: Session = Depends(get_db)):
    item = db.get(Environment, environment_id)
    if item is None:
        raise HTTPException(404, "Ambiente não encontrado.")
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@router.get("/computers", response_model=list[ComputerRead])
def list_computers(environment_id: int | None = None, db: Session = Depends(get_db)):
    query = select(Computer).order_by(Computer.sort_order, Computer.name)
    if environment_id is not None:
        query = query.where(Computer.environment_id == environment_id)
    return db.scalars(query).all()


@router.post("/computers", response_model=ComputerRead, status_code=201)
def create_computer(body: ComputerCreate, db: Session = Depends(get_db)):
    if body.environment_id is not None and db.get(Environment, body.environment_id) is None:
        raise HTTPException(404, "Ambiente não encontrado.")
    item = Computer(**body.dict())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Já existe um computador cadastrado com esse host.") from exc
    db.refresh(item)
    return item


@router.patch("/computers/{computer_id}", response_model=ComputerRead)
def update_computer(computer_id: int, body: ComputerUpdate, db: Session = Depends(get_db)):
    item = db.get(Computer, computer_id)
    if item is None:
        raise HTTPException(404, "Computador não encontrado.")
    updates = body.dict(exclude_unset=True)
    if updates.get("environment_id") is not None and db.get(Environment, updates["environment_id"]) is None:
        raise HTTPException(404, "Ambiente não encontrado.")
    for key, value in updates.items():
        setattr(item, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Já existe um computador cadastrado com esse host.") from exc
    db.refresh(item)
    return item


@router.delete("/computers/{computer_id}", status_code=204)
def delete_computer(computer_id: int, db: Session = Depends(get_db)):
    item = db.get(Computer, computer_id)
    if item is None:
        raise HTTPException(404, "Computador não encontrado.")
    db.delete(item)
    db.commit()
    return Response(status_code=204)
