from pydantic import BaseModel


class HumanGateResponse(BaseModel):
    decision_id: str
    gate_token: str
    decision: str
    approver: str
    approver_role: str
    note: str
