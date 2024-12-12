import json
import pika
import uuid
import logging
from PyQt5.QtCore import QThread, pyqtSignal
from queue import Queue, Empty
import time


class RabbitMQWorker(QThread):
    response_received = pyqtSignal(dict)
    connection_error = pyqtSignal(str)

    def __init__(self, broker_host, broker_port, request_queue, response_queue):
        super().__init__()
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.request_queue_name = request_queue
        self.response_queue = response_queue
        self.running = True
        self.request_queue = Queue()

    def run(self):
        try:
            credentials = pika.PlainCredentials('guest', 'guest')
            connection_params = pika.ConnectionParameters(
                host=self.broker_host,
                port=self.broker_port,
                credentials=credentials
            )
            self.connection = pika.BlockingConnection(connection_params)
            self.channel = self.connection.channel()

            self.channel.queue_declare(queue=self.request_queue_name, durable=True)
            self.channel.queue_declare(queue=self.response_queue, auto_delete=True)

            logging.info(f"Ïîäêëþ÷åíèå ê RabbitMQ: host={self.broker_host}, port={self.broker_port}")

            while self.running:
                try:
                    request = self.request_queue.get(timeout=1)
                    if request:
                        self.process_request(request)
                except Empty:
                    continue
        except Exception as e:
            logging.error(f"Îøèáêà ïîäêëþ÷åíèÿ: {str(e)}")
            self.connection_error.emit(f"Îøèáêà ïîäêëþ÷åíèÿ: {str(e)}")

    def process_request(self, request):
        try:
            number = request['number']
            process_time = request['process_time']
            request_id = str(uuid.uuid4())
            return_address = self.response_queue

            # Ôîðìèðîâàíèå çàïðîñà
            request_body = json.dumps({
                "return_address": return_address,
                "request_id": request_id,
                "request": number,
                "proccess_time_in_seconds": process_time
            })

            # Ïóáëèêàöèÿ ñîîáùåíèÿ â î÷åðåäü çàïðîñîâ
            self.channel.basic_publish(
                exchange='',
                routing_key=self.request_queue_name,
                body=request_body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Ñäåëàòü ñîîáùåíèå ïîñòîÿííûì
                )
            )
            logging.info(f"Îòïðàâëåí çàïðîñ: {request_body}")

            # Îæèäàíèå îòâåòà îò ñåðâåðà
            for method_frame, properties, body in self.channel.consume(self.response_queue, auto_ack=True):
                response = json.loads(body.decode())
                if response.get("request_id") == request_id:
                    logging.info(f"Ïîëó÷åí îòâåò: {response}")
                    self.response_received.emit(response)
                    # Ïðåêðàùàåì ïîòðåáëåíèå ïîñëå ïîëó÷åíèÿ íóæíîãî îòâåòà
                    self.channel.cancel()
                    break
                else:
                    logging.warning(f"Èãíîðèðóåì îòâåò: {response}")
        except Exception as e:
            logging.error(f"Îøèáêà îáðàáîòêè çàïðîñà: {str(e)}")
            self.connection_error.emit(f"Îøèáêà îáðàáîòêè çàïðîñà: {str(e)}")

    def send_request(self, number, process_time):
        """
        Ìåòîä äëÿ äîáàâëåíèÿ çàïðîñà â î÷åðåäü.
        """
        request = {
            "number": number,
            "process_time": process_time
        }
        self.request_queue.put(request)
        logging.debug(f"Çàïðîñ äîáàâëåí â î÷åðåäü: {request}")

    def stop(self):
        """
        Ìåòîä äëÿ îñòàíîâêè ïîòîêà.
        """
        self.running = False
        self.wait()  # Æäåì çàâåðøåíèÿ ïîòîêà
        if self.connection and not self.connection.is_closed:
            self.connection.close()
        logging.info("Ðàáî÷èé ïîòîê RabbitMQ îñòàíîâëåí")