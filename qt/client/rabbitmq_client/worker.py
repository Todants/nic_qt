import pika
import logging
from PyQt5.QtCore import QThread, pyqtSignal


class RabbitMQWorker(QThread):
    response_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.connection = None
        self.channel = None
        self.running = True

    def run(self):
        try:
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=self.config["host"], port=self.config["port"])
            )
            self.channel = self.connection.channel()

            self.channel.queue_declare(queue=self.config["queue_name"])
            self.log("DEBUG: Ïîäêëþ÷åíèå ê RabbitMQ âûïîëíåíî.")

            while self.running:
                method_frame, header_frame, body = self.channel.basic_get(queue=self.config["queue_name"])
                if body:
                    self.response_received.emit(body.decode())
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            if self.connection:
                self.connection.close()

    def stop(self):
        self.running = False
        self.quit()
