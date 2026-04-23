from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.repositories.sql_repositories import SQLAddressRepository, SQLUserRepository
from ...database.session import get_db
from ....application.dtos.schemas import AddressInput, AddressOut, UserOut, UserUpdateInput
from ....auth import get_current_user
from ....domain.models.entities import Address, User


router = APIRouter(prefix="/users", tags=["Usuarios"])


@router.get("/me/addresses", response_model=list[AddressOut])
async def my_addresses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await SQLAddressRepository(db).get_by_user(current_user.id)


@router.post("/me/addresses", response_model=AddressOut, status_code=201)
async def add_address(
    data: AddressInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repository = SQLAddressRepository(db)
    address = Address(id=None, user_id=current_user.id, **data.model_dump())
    saved = await repository.create(address)
    if data.is_default:
        await repository.set_default(current_user.id, saved.id)
    return saved


@router.delete("/me/addresses/{address_id}", status_code=204)
async def delete_address(
    address_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repository = SQLAddressRepository(db)
    address = await repository.get_by_id(address_id)
    if not address or address.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Direccion no encontrada")
    await repository.delete(address_id)


@router.patch("/me", response_model=UserOut)
async def update_profile(
    data: UserUpdateInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.first_name:
        current_user.first_name = data.first_name
    if data.last_name:
        current_user.last_name = data.last_name
    if data.phone:
        current_user.phone = data.phone
    return await SQLUserRepository(db).update(current_user)
