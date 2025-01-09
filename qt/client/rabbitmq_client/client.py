import datetime
import logging
import sys
import time
import uuid
from urllib.parse import urlparse

import pika
import yaml
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, QRegExp
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QTextEdit, QVBoxLayout, QHBoxLayout, QWidget, QLineEdit, QDialog, QScrollArea, QComboBox, QMessageBox
)

from qt.protos import messages_pb2

logging.basicConfig(level=logging.DEBUG)


def load_config():
    try:
        with open("../../config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        config = {"client_log_level": "INFO", "log_path": "/var/log/app.log"}
        raise ValueError
    return config


def save_config(config):
    with open("../../config.yaml", "w") as file:
        yaml.dump(config, file)


class ClientState:
    READY = "Готов"
    WAITING = "Ожидание ответа от сервера"
    PROCESSING = "Обработка запроса"


class RabbitMQWorker(QThread):
    response_received = pyqtSignal(dict)
    connection_error = pyqtSignal(str)
    send_request_signal = pyqtSignal(int, float)

    def __init__(self, broker_url, request_queue, response_queue, timeout):
        super().__init__()
        self.broker_url = broker_url
        self.request_queue = request_queue
        self.response_queue = response_queue
        self.request_id = None
        self.running = False
        self.timeout = timeout

        parsed_url = urlparse(self.broker_url)
        if parsed_url.scheme != 'amqp':
            raise ValueError("Invalid broker URL. Must start with 'amqp://'")

        connection_params = pika.ConnectionParameters(
            host=parsed_url.hostname,
            port=parsed_url.port,
            heartbeat=600,
            blocked_connection_timeout=self.timeout
        )
        self.connection = pika.BlockingConnection(connection_params)
        self.channel = self.connection.channel()

        self.channel.queue_declare(queue=self.response_queue, durable=True)
        self.channel.queue_purge(queue=self.response_queue)

        self.send_request_signal.connect(self._process_request)

    def _process_request(self, number, process_time):
        while True:
            try:
                self.request_id = str(uuid.uuid4())

                request = messages_pb2.Request(
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
                    response = messages_pb2.Response()
                    response.ParseFromString(body)

                    if response.request_id == self.request_id:
                        logging.info(f"Получен ответ: {response}")
                        self.response_received.emit({
                            "status": "200",
                            "response": {
                                "request_id": response.request_id,
                                "result": response.response
                            }
                        })
                        break
                    else:
                        self.response_received.emit({
                            "status": "204"
                        })
                        logging.warning(f"Пропущен неподходящий ответ: {response}")
                    self.channel.basic_ack(method_frame.delivery_tag)

            except Exception as e:
                logging.error("Ошибка соединения, перезапускаем соединение.")
                self._reconnect()
                time.sleep(2)


class ClientApp(QMainWindow):
    state_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RabbitMQ Client")
        self.setGeometry(100, 100, 620, 400)

        self.config = load_config()
        self.broker_url = self.config["broker_url"]
        self.config["uuid"] = self.response_queue = str(uuid.uuid4()) if self.config["uuid"] == "None" else self.config[
            "uuid"]

        self.init_ui()

        self.worker = RabbitMQWorker(
            broker_url=self.broker_url,
            request_queue=self.config["request_queue"],
            response_queue=self.response_queue,
            timeout=self.config["connection_timeout"]
        )
        self.worker.response_received.connect(self.handle_response)
        self.worker.connection_error.connect(self.handle_error)

        self.current_state = None
        self.update_state(ClientState.READY)

    def init_ui(self):
        self.number_input = QDoubleSpinBox(self)
        self.number_input.setRange(-1073741824, 1073741823)  # Установите допустимый диапазон значений
        self.number_input.setDecimals(2)

        self.time_input = QDoubleSpinBox(self)
        self.time_input.setRange(0.0, 100000.0)
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
        self.settings_dialog = SettingsDialog(config=self.config, parent_state=self.current_state, parent=self)
        self.settings_dialog.settings_updated.connect(self.update_config)
        self.settings_dialog.exec_()

    def update_config(self, new_config):
        self.config = new_config
        save_config(self.config)

    def update_state(self, state):
        self.current_state = state
        self.state_label.setText(f"Состояние: {state}")
        self.state_changed.emit(state)
        self.send_button.setEnabled(state == ClientState.READY)
        self.cancel_button.setEnabled(state == ClientState.WAITING)

    def send_request(self):
        number = self.number_input.value()
        process_time = self.time_input.value() if self.time_checkbox.isChecked() else 0

        self.log(f"Отправка запроса, число={number}, время обработки={process_time}", level="INFO")
        self.update_state(ClientState.WAITING)

        self.worker.send_request_signal.emit(number, process_time)

        if not self.worker.isRunning():
            self.worker.start()

    def cancel_request(self):
        self.log("Пользователь отменил запрос", level="INFO")
        self.update_state(ClientState.READY)

    @pyqtSlot(dict)
    def handle_response(self, response):
        if response['status'] == "200":
            self.log(f"Получен ответ: {response['response']}", level="INFO")
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
        self.channel.close()
        self.connection.close()

        if self.worker.isRunning():
            self.worker.running = False
            self.worker.stop()
        event.accept()


class SettingsDialog(QDialog):
    settings_updated = pyqtSignal(dict)

    def __init__(self, config, parent_state, parent):
        super().__init__(parent)
        self.setGeometry(300, 300, 380, 310)
        self.config = config
        self.parent_state = parent_state
        self.setWindowTitle("Настройки")

        parent.state_changed.connect(self.handle_state_change)

        self.inputs = {}

        main_layout = QVBoxLayout()

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        labels = {
            "broker_url": "Адрес брокера",
            "log_path": "Путь к логу",
            "request_queue": "Очередь запросов",
            "response_queue": "Очередь ответов",
            "log_level": "Уровень логирования",
            "uuid": "UUID",
            "connection_timeout": "Таймаут подключения",
        }

        log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for key, value in self.config.items():
            row_layout = QHBoxLayout()
            label = QLabel(labels[key], self)

            if key == "connection_timeout":
                input_field = QSpinBox(self)
                input_field.setRange(1, 60)
                input_field.setValue(int(value))

            elif key in ["broker_url", "request_queue", "response_queue"]:
                input_field = QLineEdit(self)
                input_field.setText(str(value))
                input_field.setReadOnly(True)

            elif key == "log_level":
                input_field = QComboBox(self)
                input_field.addItems(log_levels)
                input_field.setCurrentText(str(value))

            elif key == "uuid":
                input_field = QLineEdit(self)
                input_field.setText(str(value))
                generate_button = QPushButton("Сгенерировать", self)
                generate_button.clicked.connect(lambda: self.generate_uuid(input_field))
                row_layout.addWidget(generate_button)

            else:
                input_field = QLineEdit(self)
                input_field.setText(str(value))

            self.inputs[key] = input_field
            row_layout.addWidget(label)
            row_layout.addWidget(input_field)
            scroll_layout.addLayout(row_layout)

        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)

        save_button = QPushButton("Сохранить", self)
        save_button.clicked.connect(self.save_settings)
        main_layout.addWidget(save_button)

        self.setLayout(main_layout)

    def save_settings(self):
        if self.parent_state == ClientState.WAITING:
            QMessageBox.warning(self, "Запрещено", "Нельзя изменять настройки в состоянии ОЖИДАНИЯ.")
            return
        for key, input_field in self.inputs.items():
            if isinstance(input_field, QSpinBox):
                self.config[key] = input_field.value()
            elif isinstance(input_field, QComboBox):
                self.config[key] = input_field.currentText()
            else:
                self.config[key] = input_field.text()
        self.settings_updated.emit(self.config)
        self.close()

    def handle_state_change(self, state):
        self.parent_state = ClientState.READY

    @staticmethod
    def generate_uuid(input_field):
        new_uuid = str(uuid.uuid4())
        input_field.setText(new_uuid)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    client_app = ClientApp()
    client_app.show()
    sys.exit(app.exec_())
