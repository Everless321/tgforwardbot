from pydantic import BaseModel


class SendCodeRequest(BaseModel):
    phone: str


class VerifyCodeRequest(BaseModel):
    code: str


class TwoFARequest(BaseModel):
    password: str


class UserInfo(BaseModel):
    phone: str
    first_name: str
    username: str | None


class AuthStatusResponse(BaseModel):
    authorized: bool
    user: UserInfo | None


class AuthActionResponse(BaseModel):
    status: str
    user: UserInfo | None = None
