import asyncio
import logging
import os
import sys

import yaml
from aio_pika import connect, IncomingMessage, Message, ExchangeType

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../protos')))
from messages_pb2 import Request, Response
from utils import double_number


with open("../../config.yaml", "r") as f:
    config = yaml.safe_load(f)

logging.basicConfig(
    level=getattr(logging, config["log_level"]),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config["log_path"]),
        logging.StreamHandler()
    ]
)


async def handle_request(message: IncomingMessage):
    async with message.process():
        request = Request()
        request.ParseFromString(message.body)
        logging.info(f"Получен запрос {request}")

        response_data = {
            "request_id": request.request_id,
            "response": double_number(request.request)
        }

        await asyncio.sleep(request.proccess_time_in_seconds)

        connection = await connect(config["broker_url"])
        channel = await connection.channel()

        return_address = request.return_address
        response_message = Response(
            request_id=request.request_id,
            response=double_number(request.request)
        )
        response_message_data = response_message.SerializeToString()

        await channel.default_exchange.publish(
            Message(body=response_message_data),
            routing_key=return_address
        )
        logging.info(f"Ответ отправлен в {return_address}: {response_data}")


async def main():
    while True:
        try:
            connection = await connect(config["broker_url"])
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                'direct_exchange',
                ExchangeType.DIRECT
            )
            queue = await channel.declare_queue(config["request_queue"])
            logging.info("Сервер готов принимать запросы")

            await queue.consume(handle_request)
            await asyncio.Future()
        except Exception as e:
            logging.error(f"Ошибка: {e}. Повторная попытка подключиться через 5 секунд.")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
