import asyncio
import logging
import yaml
from aio_pika import connect, IncomingMessage, Message, ExchangeType
from qt.protos import messages_pb2
from qt.server.rabbitmq_server.utils import double_number

with open("../../config.yaml", "r") as f:
    config = yaml.safe_load(f)


def setup_logging(log_level, log_path):
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    stream_handler = logging.StreamHandler()

    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[file_handler, stream_handler]
    )
    logging.info("Логирование обновлено")


# Первоначальная настройка
setup_logging(config["log_level"], config["log_path"])


async def handle_request(message: IncomingMessage):
    async with message.process():
        request = messages_pb2.Request()
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
        response_message = messages_pb2.Response(
            request_id=request.request_id,
            response=double_number(request.request)
        )
        response_message_data = response_message.SerializeToString()

        await channel.default_exchange.publish(
            Message(body=response_message_data),
            routing_key=return_address
        )
        logging.info(f"Ответ отправлен в {return_address}: {response_data}")


async def monitor_config_changes():
    last_config = config.copy()

    while True:
        await asyncio.sleep(2)
        try:
            with open("../../config.yaml", "r") as file:
                new_config = yaml.safe_load(file)

            if (new_config["log_level"] != last_config["log_level"] or
                    new_config["log_path"] != last_config["log_path"]):
                setup_logging(new_config["log_level"], new_config["log_path"])
                last_config.update(new_config)

        except Exception as e:
            logging.error(f"Ошибка чтения конфига: {e}")


async def main():
    asyncio.create_task(monitor_config_changes())

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
