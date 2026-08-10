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


class ResetlessFakeSerial(FakeSerial):
    """포트를 열어도 리셋되지 않는 네이티브 USB 보드(예: UNO R4 WiFi)를 흉내낸다.

    부팅 시의 READY 를 (이미 지나가버려서) 보내지 않는다. 대신 PING 을 받았을
    때만 OK PING 으로 답한다. connect() 가 READY 만 기다리면 영원히 못 붙고,
    PING 을 능동적으로 찔러야만 연결이 된다.
    """

    def write(self, data):
        super().write(data)
        if data == b"PING\n":
            self._pending.append("OK PING")


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


def test_connect_probes_with_ping_when_board_sends_no_ready():
    # UNO R4 WiFi 등 네이티브 USB 보드는 포트를 열어도 리셋되지 않아 부팅 READY 를
    # 놓친다. connect() 는 PING 을 능동적으로 보내 OK PING 으로도 연결을 확인해야 한다.
    fake = ResetlessFakeSerial([])
    controller = tile_protocol.TileController(
        serial_factory=lambda port, baud, read_timeout: fake)
    controller.connect("/dev/fake", ready_timeout=1.0)
    assert controller.simulated is False
    assert b"PING\n" in fake.written


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
    # 설계 문서 §7.3: 응답 대기가 영상 루프를 오래 막으면 안 된다.
    # 상한은 RESPONSE_TIMEOUT 에 매어 둔다 - 숫자를 그대로 적어두면 타임아웃을
    # 조정할 때마다 이 테스트가 관계없이 깨진다.
    assert time.monotonic() - started < tile_protocol.RESPONSE_TIMEOUT + 0.3


class SlowFakeSerial(FakeSerial):
    """OK 를 보내기 전에 펌웨어처럼 뜸을 들이는 보드.

    실제 펌웨어의 handleFire 는 덮개를 연 뒤 SEQ_DELAY_MS(200ms) 를 기다렸다가
    타일을 올리고, 그 **뒤에** OK 를 보낸다.
    """

    def __init__(self, responses=None, delay=0.0, reply=None):
        super().__init__(responses)
        self._delay = delay
        self._reply = reply

    def write(self, data):
        super().write(data)
        if self._reply is not None and data != b"PING\n":
            time.sleep(self._delay)
            self._pending.append(self._reply)


def test_ack_is_accepted_when_board_replies_after_its_move_delay():
    """펌웨어가 서보를 다 움직인 뒤 OK 를 보내도 ack 를 놓치지 않는다.

    회귀 테스트다. RESPONSE_TIMEOUT 이 펌웨어의 SEQ_DELAY_MS 와 똑같이 0.2 였을
    때, 응답이 매번 데드라인 직후에 도착해 ack 가 항상 False 로 돌아왔다.
    아두이노는 멀쩡히 움직이는데 main.py 는 ack 를 보고 화면 타일을 켜므로,
    '서보만 움직이고 화면은 가만히 있는' 증상이 났다.
    """
    fake = SlowFakeSerial(["READY 4"], delay=0.25, reply="OK FIRE 1")
    controller = tile_protocol.TileController(
        serial_factory=lambda port, baud, read_timeout: fake
    )
    controller.connect("/dev/fake")
    assert controller.fire({1}) is True


def test_response_timeout_exceeds_firmware_move_delay():
    """타임아웃은 펌웨어의 동작 지연보다 넉넉히 커야 한다.

    펌웨어(hardware/four_servo_control)의 SEQ_DELAY_MS 는 200ms 다. 이 값을
    늘리면 여기 상수도 같이 올려야 한다 - 안 그러면 위 회귀가 되살아난다.
    """
    firmware_move_delay = 0.2
    assert tile_protocol.RESPONSE_TIMEOUT > firmware_move_delay * 2


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


def test_connect_to_simulation_closes_previous_serial_handle():
    # 실제 포트로 연결한 후 None 으로 연결하면 첫 번째 핸들이 닫혀야 한다.
    fake = FakeSerial(["READY 4"])

    def factory(port, baud, read_timeout):
        return fake

    controller = tile_protocol.TileController(serial_factory=factory)
    assert controller.connect("/dev/fake") == 4
    assert fake.closed is False

    assert controller.connect(None) == 0
    assert controller.simulated is True
    assert fake.closed is True
    assert fake.close_count == 1
