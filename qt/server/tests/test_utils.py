from server.rabbitmq_server.utils import double_number

def test_double_number():
    assert double_number(2) == 4
    assert double_number(-3) == -6
    assert double_number(0) == 0
