import datetime
import json
import os
import sys
import time
import uuid
import logging
import pika
import yaml
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QTextEdit, QVBoxLayout, QHBoxLayout, QWidget, QLineEdit
)
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
from pika.exchange_type import ExchangeType

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../protos')))
from messages_pb2 import Request, Response

logging.basicConfig(level=logging.DEBUG)

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)


class ClientState:
    READY = "Готов"
    WAITING = "Ожидание ответа от сервера"
    PROCESSING = "Обработка запроса"


class RabbitMQWorker(QThread):
    response_received = pyqtSignal(dict)
    connection_error = pyqtSignal(str)
    send_request_signal = pyqtSignal(int, float)

    def __init__(self, broker_url, request_queue, response_queue):
        super().__init__()
        self.broker_url = broker_url
        self.request_queue = request_queue
        self.response_queue = response_queue
        self.request_id = None

        try:
            self.connection = pika.BlockingConnection(pika.URLParameters(self.broker_url))
            self.channel = self.connection.channel()
            """self.channel.exchange_declare(
                exchange='direct',
                exchange_type=ExchangeType.direct,
                durable=True,
                auto_delete=False,
            )
            self.channel.queue_declare(
                queue=self.request_queue,
                durable=True,
                exclusive=False,
                auto_delete=False,
            )
            self.channel.queue_bind(
                self.request_queue,
                'direct',
                routing_key=self.request_queue,
            )"""
            self.channel.queue_declare(
                queue=self.response_queue,
                auto_delete=True,
            )
            #self.channel.confirm_delivery()
        except Exception as e:
            logging.error(f"Ошибка подключения к RabbitMQ: {str(e)}")
            self.connection_error.emit(f"Ошибка подключения: {str(e)}")

        self.send_request_signal.connect(self._process_request)

    def _process_request(self, number, process_time):
        for _ in range(5):
            try:
                self.request_id = str(uuid.uuid4())

                request = Request(
                    return_address=self.response_queue,
                    request_id=self.request_id,
                    request=number,
                    proccess_time_in_seconds=process_time,
                )

                self.channel.basic_publish(
                    exchange='',
                    routing_key=self.request_queue,
                    body=request.SerializeToString()
                )
                logging.info(f"Отправлен запрос: {request}")

                break

            except pika.exceptions.AMQPChannelError:
                logging.error("Ошибка канала, перезапускаем соединение и канал.")
                self._reconnect()
                time.sleep(2)

            except pika.exceptions.AMQPConnectionError:
                logging.error("Ошибка соединения, перезапускаем соединение.")
                self._reconnect()
                time.sleep(2)

            except Exception as e:
                logging.error(f"Ошибка отправки запроса: {str(e)}")
                self.connection_error.emit(f"Ошибка отправки запроса: {str(e)}")

    def _reconnect(self):
        try:
            if self.connection.is_open:
                self.connection.close()
            self.connection = pika.BlockingConnection(pika.URLParameters(self.broker_url))
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue=self.response_queue, auto_delete=True)
            logging.info("Переподключение выполнено успешно.")
        except Exception as e:
            logging.error(f"Ошибка переподключения: {str(e)}")
            self.connection_error.emit(f"Ошибка переподключения: {str(e)}")

    def stop(self):
        if self.connection.is_open:
            self.connection.close()
            logging.info("Соединение с RabbitMQ закрыто.")

    def run(self):
        for _ in range(5):
            try:
                for method_frame, properties, body in self.channel.consume(self.response_queue):
                    response = Response()
                    response.ParseFromString(body)

                    if response.request_id == self.request_id:
                        logging.info(f"Получен ответ: {response}")
                        self.response_received.emit({
                            "status": "OK",
                            "response": {
                                "request_id": response.request_id,
                                "result": response.response
                            }
                        })

                        self.channel.basic_ack(method_frame.delivery_tag)
                        break
                    else:
                        logging.warning(f"Пропущен неподходящий ответ: {response}")
                        self.channel.basic_ack(method_frame.delivery_tag)

            except pika.exceptions.AMQPChannelError:
                logging.error("Ошибка канала, перезапускаем соединение и канал.")
                self._reconnect()
                time.sleep(2)

            except pika.exceptions.AMQPConnectionError:
                logging.error("Ошибка соединения, перезапускаем соединение.")
                self._reconnect()
                time.sleep(2)

            except Exception as e:
                logging.error(f"Ошибка отправки запроса: {str(e)}")
                self.connection_error.emit(f"Ошибка отправки запроса: {str(e)}")


class ClientApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RabbitMQ Client")
        self.setGeometry(100, 100, 600, 400)

        self.broker_url = config["broker_url"]
        self.request_queue = config["request_queue"]
        self.response_queue = str(uuid.uuid4())

        self.current_state = ClientState.READY

        self.init_ui()

        self.worker = RabbitMQWorker(
            broker_url=self.broker_url,
            request_queue=self.request_queue,
            response_queue=self.response_queue
        )
        self.worker.response_received.connect(self.handle_response)
        self.worker.connection_error.connect(self.handle_error)

    def init_ui(self):
        self.number_input = QSpinBox(self)
        self.number_input.setRange(0, 1000)

        self.time_input = QDoubleSpinBox(self)
        self.time_input.setRange(0.1, 10.0)
        self.time_input.setValue(1.0)
        self.time_checkbox = QCheckBox("Время обработки:", self)
        self.time_checkbox.setChecked(False)
        self.time_input.setEnabled(False)
        self.time_checkbox.stateChanged.connect(
            lambda state: self.time_input.setEnabled(self.time_checkbox.isChecked())
        )

        self.send_button = QPushButton("Отправить запрос", self)
        self.cancel_button = QPushButton("Отменить запрос", self)
        self.cancel_button.setEnabled(False)
        self.send_button.clicked.connect(self.send_request)
        self.cancel_button.clicked.connect(self.cancel_request)

        self.state_label = QLabel("Состояние: Готов", self)
        self.response_label = QLabel("Ответ: ", self)

        self.log_widget = QTextEdit(self)
        self.log_widget.setReadOnly(True)

        main_layout = QVBoxLayout()
        input_layout = QHBoxLayout()
        button_layout = QHBoxLayout()

        input_layout.addWidget(QLabel("Число:"))
        input_layout.addWidget(self.number_input)
        input_layout.addWidget(self.time_checkbox)
        input_layout.addWidget(self.time_input)

        button_layout.addWidget(self.send_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(input_layout)
        main_layout.addWidget(self.state_label)
        main_layout.addWidget(self.response_label)
        main_layout.addLayout(button_layout)
        main_layout.addWidget(QLabel("Лог событий:"))
        main_layout.addWidget(self.log_widget)

        central_widget = QWidget(self)
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def update_state(self, state):
        self.current_state = state
        self.state_label.setText(f"Состояние: {state}")
        if state == ClientState.READY:
            self.send_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
        elif state == ClientState.WAITING:
            self.send_button.setEnabled(False)
            self.cancel_button.setEnabled(True)

    def send_request(self):
        number = self.number_input.value()
        process_time = self.time_input.value() if self.time_checkbox.isChecked() else 0

        self.log(f"Отправка запроса, число={number}, время обработки={process_time}", level="INFO")
        self.update_state(ClientState.WAITING)

        self.worker.send_request_signal.emit(number, process_time)
        self.worker.start()

    def cancel_request(self):
        self.worker.stop()
        self.log("Пользователь отменил запрос", level="INFO")
        self.update_state(ClientState.READY)

    @pyqtSlot(dict)
    def handle_response(self, response):
        if self.current_state == ClientState.WAITING:
            self.log(f"Получен ответ: {response}", level="INFO")
            self.response_label.setText(f"Ответ: {response['response']['result']}")
            self.update_state(ClientState.READY)
        else:
            self.log("Ответ игнорируется, запрос отменен", level="INFO")

    @pyqtSlot(str)
    def handle_error(self, error_message):
        self.log(f"Ошибка: {error_message}", level="ERROR")
        self.update_state(ClientState.READY)

    def log(self, message, level="DEBUG"):
        now = datetime.datetime.now(datetime.timezone.utc).astimezone()
        time_format = "%Y-%m-%d %H:%M:%S"
        if level == "INFO":
            self.log_widget.append(f"({now:{time_format}}) [INFO] {message}")
        elif level == "ERROR":
            self.log_widget.append(f"({now:{time_format}}) [ERROR] {message}")
        logging.debug(message)

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    client_app = ClientApp()
    client_app.show()
    sys.exit(app.exec_())
