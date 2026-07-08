from fastapi import APIRouter

from app import schemas
from app.services import mock_store

router = APIRouter()


@router.post("/login", response_model=schemas.AuthResult)
async def login(input_data: schemas.LoginInput) -> schemas.AuthResult:
    mock_store.user.email = input_data.email
    return schemas.AuthResult(access_token=f"dev_token_{input_data.email}", user=mock_store.user)


@router.post("/register", response_model=schemas.AuthResult)
async def register(input_data: schemas.LoginInput) -> schemas.AuthResult:
    mock_store.user.email = input_data.email
    return schemas.AuthResult(access_token=f"dev_token_{input_data.email}", user=mock_store.user)


@router.post("/logout", status_code=204)
async def logout() -> None:
    return None


@router.get("/me", response_model=schemas.User)
async def me() -> schemas.User:
    return mock_store.user

