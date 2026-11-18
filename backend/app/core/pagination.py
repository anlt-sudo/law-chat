"""Phân trang theo 00-common §6: ?page=1&page_size=20 → {items, page, page_size, total}."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel


class PageParams(BaseModel):
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int

    @classmethod
    def of(cls, items: list[T], params: PageParams, total: int) -> Page[T]:
        return cls(items=items, page=params.page, page_size=params.page_size, total=total)
