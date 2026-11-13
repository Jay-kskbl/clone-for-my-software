from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """所有契约模型的基类。

    extra="forbid"：字段名写错时直接报错，而不是被悄悄丢掉。
    frozen=True：契约对象在模块之间传递，不允许中途被修改。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
