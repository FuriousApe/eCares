"""Thin helper for services that call the Data Service over gRPC.

Every call carries the current request id as metadata, so the Data Service
can stamp it onto the audit row it writes in the same transaction.
"""

from __future__ import annotations

import grpc

from libs.common.grpc_gen import dataservice_pb2_grpc
from libs.common.request_id import GRPC_METADATA_KEY, get_request_id


def data_service_channel(target: str) -> grpc.Channel:
    return grpc.insecure_channel(target)


def data_service_stub(target: str) -> dataservice_pb2_grpc.DataServiceStub:
    return dataservice_pb2_grpc.DataServiceStub(data_service_channel(target))


def call_metadata() -> tuple[tuple[str, str], ...]:
    return ((GRPC_METADATA_KEY, get_request_id()),)


async def data_service_async_channel(target: str) -> grpc.aio.Channel:
    return grpc.aio.insecure_channel(target)


async def data_service_async_stub(target: str) -> dataservice_pb2_grpc.DataServiceStub:
    channel = await data_service_async_channel(target)
    return dataservice_pb2_grpc.DataServiceStub(channel)
