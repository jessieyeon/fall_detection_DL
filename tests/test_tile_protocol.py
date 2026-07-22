import time

import tile_protocol


class FakeSerial:
    """pyserial 의 최소 인터페이스만 흉내낸다."""

    def __init__(self, responses=None):
        self.written = []
        self.closed = False
        self.close_count = 0
        self._pending = list(responses or [])

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.written.append(data)

    def readline(self):
        if self._pending:
            return (self._pending.pop(0) + "\n").encode("ascii")
        return b""

    def close(self):
        self.closed = True
        self.close_count += 1


def make_controller(responses):
    fake = FakeSerial(responses)
    controller = tile_protocol.TileController(
        serial_factory=lambda port, baud, read_timeout: fake
    )
    return controller, fake


def test_connect_returns_servo_count_from_ready_line():
    controller, _ = make_controller(["READY 4"])
    assert controller.connect("/dev/fake") == 4
    assert controller.simulated is False
    assert controller.servo_count == 4


def test_connect_skips_comment_lines_before_ready():
    controller, _ = make_controller(["# 초기화 완료", "# FIRE 0,2", "READY 4"])
    assert controller.connect("/dev/fake") == 4


def test_connect_without_ready_falls_back_to_simulation():
    controller, fake = make_controller([])
    assert controller.connect("/dev/fake", ready_timeout=0.2) == 0
    assert controller.simulated is True
    assert fake.closed is True


def test_connect_with_no_port_is_simulation_mode():
    controller, _ = make_controller(["READY 4"])
    assert controller.connect(None) == 0
    assert controller.simulated is True


def test_connect_survives_serial_open_failure():
    def exploding_factory(port, baud, read_timeout):
        raise OSError("포트 없음")

    controller = tile_protocol.TileController(serial_factory=exploding_factory)
    assert controller.connect("/dev/nope") == 0
    assert controller.simulated is True


def test_fire_writes_sorted_csv_and_confirms_ack():
    controller, fake = make_controller(["READY 4", "OK FIRE 1,3"])
    controller.connect("/dev/fake")
    assert controller.fire({3, 1}) is True
    assert fake.written == [b"FIRE 1,3\n"]


def test_fire_single_tile():
    controller, fake = make_controller(["READY 4", "OK FIRE 2"])
    controller.connect("/dev/fake")
    assert controller.fire({2}) is True
    assert fake.written == [b"FIRE 2\n"]


def test_fire_all_four_tiles():
    controller, fake = make_controller(["READY 4", "OK FIRE 0,1,2,3"])
    controller.connect("/dev/fake")
    assert controller.fire({0, 1, 2, 3}) is True
    assert fake.written == [b"FIRE 0,1,2,3\n"]


def test_fire_with_empty_set_sends_nothing():
    controller, fake = make_controller(["READY 4"])
    controller.connect("/dev/fake")
    assert controller.fire(set()) is False
    assert fake.written == []


def test_err_response_returns_false_without_raising():
    controller, _ = make_controller(["READY 4", "ERR bad tile index"])
    controller.connect("/dev/fake")
    assert controller.fire({9}) is False


def test_missing_ack_returns_false_within_timeout():
    controller, _ = make_controller(["READY 4"])
    controller.connect("/dev/fake")
    started = time.monotonic()
    assert controller.fire({1}) is False
    # 설계 문서 §7.3: 응답 대기가 영상 루프를 오래 막으면 안 된다
    assert time.monotonic() - started < 0.5


def test_reset_and_ping():
    controller, fake = make_controller(["READY 4", "OK RESET", "OK PING"])
    controller.connect("/dev/fake")
    assert controller.reset() is True
    assert controller.ping() is True
    assert fake.written == [b"RESET\n", b"PING\n"]


def test_simulation_mode_does_not_write_or_raise():
    controller = tile_protocol.TileController()
    controller.connect(None)
    assert controller.fire({1, 3}) is False
    assert controller.reset() is False


def test_connect_ignores_malformed_ready_line_and_keeps_waiting():
    # 부팅 중 시리얼 노이즈로 "READY 4a" 같은 깨진 줄이 온 뒤 정상 READY 가 온다.
    # int() 변환 실패로 connect() 가 죽어서는 안 되고, 깨진 줄을 유효한 핸드셰이크로
    # 받아들여서도 안 된다 - 다음 줄까지 계속 기다려야 한다.
    controller, _ = make_controller(["READY 4a", "READY 4"])
    assert controller.connect("/dev/fake") == 4
    assert controller.simulated is False
    assert controller.servo_count == 4


def test_connect_with_only_malformed_ready_lines_falls_back_to_simulation():
    # 깨진 READY 줄만 계속 오고 마감 시간까지 정상 줄이 오지 않으면
    # 예외 없이 시뮬레이션 모드로 대체되어야 한다.
    controller, fake = make_controller(["READY \x00", "READY 4a"])
    assert controller.connect("/dev/fake", ready_timeout=0.2) == 0
    assert controller.simulated is True
    assert fake.closed is True


def test_reconnect_closes_previous_serial_handle():
    first_fake = FakeSerial(["READY 4"])
    second_fake = FakeSerial(["READY 4"])
    fakes = [first_fake, second_fake]

    def factory(port, baud, read_timeout):
        return fakes.pop(0)

    controller = tile_protocol.TileController(serial_factory=factory)
    assert controller.connect("/dev/fake") == 4
    assert first_fake.closed is False

    assert controller.connect("/dev/fake") == 4
    assert first_fake.closed is True
    assert first_fake.close_count == 1
    assert second_fake.closed is False
