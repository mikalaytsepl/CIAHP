import uuid
from datetime import datetime
from typing import Optional

from ninja import Schema


class OperationOut(Schema):
    id:          uuid.UUID
    playbook:    str
    extra_vars:  dict
    status:      str
    stdout:      str
    stderr:      str
    return_code: Optional[int]
    started_at:  Optional[datetime]
    finished_at: Optional[datetime]
    created_at:  datetime


class OperationListOut(Schema):
    id:         uuid.UUID
    playbook:   str
    status:     str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
