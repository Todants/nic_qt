import sys
import uuid

import yaml
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLineEdit, QPushButton, QDialog, QLabel, \
    QSpinBox, QDoubleSpinBox, QCheckBox, QTextEdit, QHBoxLayout
from client.rabbitmq_client.worker import RabbitMQWorker


# Функция для загрузки конфигурации из файла config.yaml
def load_config():
    try:
        with open("config.yaml", "r") as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        config = {"log_level": "INFO", "log_path": "/var/log/app.log"}
    return config


# Функция для сохранения конфигурации в файл config.yaml
def save_config(config):
    with open("config.yaml", "w") as file:
        yaml.dump(config, file)


class MainWindow(QMainWindow):
    def init(self):
        super().init()
        self.config = load_config()  # Загрузка начальных значений из config.yaml
        self.setWindowTitle("RabbitMQ Client")
        self.setGeometry(100, 100, 600, 400)

        self.broker_url = self.config["broker_url"]
        self.request_queue = self.config["request_queue"]
        self.response_queue = str(uuid.uuid4())

        self.current_state = "READY"
        self.init_ui()

        # Инициализация worker с использованием значений конфигурации
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

        # Добавляем кнопку настроек
        self.settings_button = QPushButton("Настройки", self)
        self.settings_button.clicked.connect(self.open_settings)

        # Основной layout
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

    def send_request(self):
        # Логика отправки запроса
        pass

    # Отмена запроса (пример)
    def cancel_request(self):
        # Логика отмены запроса
        pass


# Диалоговое окно настроек
class SettingsDialog(QDialog):
    settings_updated = pyqtSignal(dict)

    def init(self, config, parent=None):
        super().init(parent)
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
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
