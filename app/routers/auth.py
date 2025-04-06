from fastapi import APIRouter

router = APIRouter()


@router.get("/login")
async def login():


    return {"message": "Login endpoint"}