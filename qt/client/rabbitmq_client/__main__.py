import asyncio
import uuid
import yaml
from aio_pika import connect, Message, ExchangeType

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../protos')))
from messages_pb2 import Request, Response

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)


async def send_request(number, process_time=None):
    connection = await connect(config["broker_url"])
    channel = await connection.channel()

    request_id = str(uuid.uuid4())
    return_address = config["response_queue"]

    request = Request(
        return_address=return_address,
        request_id=request_id,
        request=number,
        proccess_time_in_seconds=process_time,
    )

    message = Message(body=request.SerializeToString())

    await channel.default_exchange.publish(message, routing_key=config["request_queue"])
    print(f"Запрос отправлен: {request}")

    queue = await channel.declare_queue(return_address, auto_delete=True)
    async with queue.iterator() as queue_iter:
        async for response_message in queue_iter:
            response = Response()
            response.ParseFromString(response_message.body)
            print(f"Ответ получен: {response}")
            break


async def send_multiple_requests():
    await asyncio.gather(
        send_request(10, process_time=7),
        send_request(20, process_time=5),
        send_request(30, process_time=3)
    )


if __name__ == "__main__":
    asyncio.run(send_multiple_requests())
