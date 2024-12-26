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
    QPushButton, QTextEdit, QVBoxLayout, QHBoxLayout, QWidget, QLineEdit, QDialog
)
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../protos')))
from messages_pb2 import Request, Response

logging.basicConfig(level=logging.DEBUG)


def load_config():
    try:
        with open("../../config.yaml", "r") as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        config = {"log_level": "INFO", "log_path": "/var/log/app.log"}
        raise ValueError
    return config


def save_config(config):
    with open("../../config.yaml", "w") as file:
        yaml.dump(config, file)


class ClientState:
    READY = "Готов"
    WAITING = "Ожидание ответа от сервера"
    PROCESSING = "Обработка запроса"

#
# class RabbitMQWorker2:
#     response_received = pyqtSignal(dict)
#     connection_error = pyqtSignal(str)
#     send_request_signal = pyqtSignal(int, float)
#
#     def __init__(self, broker_url, request_queue, response_queue):
#         self.broker_url = broker_url
#         self.request_queue = request_queue
#         self.response_queue = response_queue
#         self.request_id = None
#         self.running = False
#
#         try:
#             self.connection = pika.BlockingConnection(pika.URLParameters(self.broker_url))
#             self.channel = self.connection.channel()
#             self.channel.queue_declare(queue=self.response_queue, durable=True)
#         except Exception as e:
#             logging.error(f"Ошибка подключения к RabbitMQ: {str(e)}")
#             self.connection_error.emit(f"Ошибка подключения: {str(e)}")
#
#         self.send_request_signal.connect(self._process_request)


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
        self.running = False

        # try:
        connection_params = pika.ConnectionParameters(
            host=self.broker_url,
            heartbeat=600
        )
        self.connection = pika.BlockingConnection(pika.URLParameters(self.broker_url))
        self.channel = self.connection.channel()

        self.channel.queue_declare(queue=self.response_queue, durable=True)
        self.channel.queue_purge(queue=self.response_queue)
        # except Exception as e:
        #     logging.error(f"Ошибка подключения к RabbitMQ: {str(e)}")
        #     self.connection_error.emit(f"Ошибка подключения: {str(e)}")

        self.send_request_signal.connect(self._process_request)

    def _process_request(self, number, process_time):
        while True:
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
            self.channel.queue_declare(queue=self.response_queue, durable=True)

            logging.info("Переподключение выполнено успешно.")
        except Exception as e:
            logging.error(f"Ошибка переподключения: {str(e)}")
            self.connection_error.emit(f"Ошибка переподключения: {str(e)}")

    def stop(self):
        if self.connection.is_open:
            self.connection.close()
            logging.info("Соединение с RabbitMQ закрыто.")

    def run(self):
        while True:
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

            except Exception as e:
                logging.error("Ошибка соединения, перезапускаем соединение.")
                self._reconnect()
                time.sleep(2)


class ClientApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RabbitMQ Client")
        self.setGeometry(100, 100, 600, 400)

        self.config = load_config()
        self.broker_url = self.config["broker_url"]
        self.request_queue = self.config["request_queue"]
        self.response_queue = str(uuid.uuid4())

        self.init_ui()

        self.worker = RabbitMQWorker(
            broker_url=self.broker_url,
            request_queue=self.request_queue,
            response_queue=self.response_queue
        )
        self.worker.response_received.connect(self.handle_response)
        self.worker.connection_error.connect(self.handle_error)

        self.current_state = None
        self.update_state(ClientState.READY)

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

        self.settings_button = QPushButton("Настройки", self)
        self.settings_button.clicked.connect(self.open_settings)

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
        main_layout.addWidget(self.settings_button)

        central_widget = QWidget(self)
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def open_settings(self):
        self.settings_dialog = SettingsDialog(self.config)
        self.settings_dialog.settings_updated.connect(self.update_config)
        self.settings_dialog.exec_()

    def update_config(self, new_config):
        self.config = new_config
        save_config(self.config)

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

        if not self.worker.isRunning():
            self.worker.start()

    def cancel_request(self):
        if self.worker.isRunning():
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
        if self.worker.isRunning():
            self.worker.stop()
        event.accept()


class SettingsDialog(QDialog):
    settings_updated = pyqtSignal(dict)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Настройки")

        self.log_level_input = QLineEdit(self)
        self.log_level_input.setText(self.config["log_level"])

        self.log_path_input = QLineEdit(self)
        self.log_path_input.setText(self.config["log_path"])

        self.save_button = QPushButton("Сохранить", self)
        self.save_button.clicked.connect(self.save_settings)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Уровень логирования:"))
        layout.addWidget(self.log_level_input)
        layout.addWidget(QLabel("Путь к логу:"))
        layout.addWidget(self.log_path_input)
        layout.addWidget(self.save_button)

        self.setLayout(layout)

    def save_settings(self):
        self.config["log_level"] = self.log_level_input.text()
        self.config["log_path"] = self.log_path_input.text()
        self.settings_updated.emit(self.config)  # Отправляем обновленные данные родительскому окну
        self.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    client_app = ClientApp()
    client_app.show()
    sys.exit(app.exec_())
