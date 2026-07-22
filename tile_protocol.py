"""아두이노 타일 컨트롤러와의 줄 단위 텍스트 프로토콜.

의존성은 pyserial 뿐이다. mediapipe, opencv 에 의존하지 않는다.

프로토콜 (설계 문서 §7):
    파이썬 -> 아두이노     FIRE 1,3   RESET   PING
    아두이노 -> 파이썬     READY 4    OK FIRE 1,3   OK RESET   OK PING
                          ERR <사유>   # <사람이 읽을 주석, 무시됨>

타일 번호는 0-indexed 로 전선 위를 그대로 흐른다. 타일 번호와 PCA9685 채널의
매핑은 펌웨어 안에만 존재한다.
"""

import time

BAUD = 115200
SERIAL_READ_TIMEOUT = 0.05   # readline() 한 번이 블로킹되는 최대 시간(초)
RESPONSE_TIMEOUT = 0.2       # 명령 하나에 대한 응답을 기다리는 최대 시간(초)
POLL_INTERVAL = 0.01         # 대기 루프가 CPU 를 독점하지 않도록 잠깐 양보하는 시간(초)


def _default_serial_factory(port, baud, read_timeout):
    import serial  # 시뮬레이션 모드만 쓸 때 pyserial 을 강제하지 않으려고 지연 임포트

    return serial.Serial(port, baud, timeout=read_timeout)


class TileController:
    """타일 서보를 제어한다. 어떤 실패에도 예외를 밖으로 던지지 않는다.

    시연 도중 시리얼이 한 번 꼬였다고 프로그램이 죽는 것이 최악이므로,
    모든 명령은 성공 여부를 bool 로만 알린다.
    """

    def __init__(self, serial_factory=None):
        self._factory = serial_factory or _default_serial_factory
        self._serial = None
        self.simulated = True
        self.servo_count = 0

    # --- 연결 ---

    def connect(self, port, baud=BAUD, ready_timeout=5.0):
        """포트를 열고 READY 를 기다린다. 사용 가능한 서보 개수를 반환한다.

        대부분의 아두이노는 시리얼 포트가 열릴 때 리셋되고 setup() 에는
        delay(500) 이 있다. 핸드셰이크 없이 바로 명령을 보내면 부팅 중에
        삼켜진다.
        """
        self._close_serial()  # 재연결 시 이전 핸들이 열린 채로 새지 않도록 먼저 닫는다

        if not port:
            print("[타일] 시리얼 포트가 지정되지 않음 - 시뮬레이션 모드로 실행합니다.")
            return self._fall_back_to_simulation()

        try:
            self._serial = self._factory(port, baud, SERIAL_READ_TIMEOUT)
        except Exception as exc:
            print(f"[타일] 경고: {port} 를 열 수 없습니다 ({exc}) - 시뮬레이션 모드.")
            return self._fall_back_to_simulation()

        try:
            self._serial.reset_input_buffer()
        except Exception:
            pass

        deadline = time.monotonic() + ready_timeout
        while time.monotonic() < deadline:
            line = self._read_line()
            if line is None:
                time.sleep(POLL_INTERVAL)  # 아직 못 읽었으면 잠깐 쉬었다가 다시 시도
                continue
            if line.startswith("READY"):
                parts = line.split()
                if len(parts) > 1:
                    try:
                        servo_count = int(parts[1])
                    except ValueError:
                        # 부팅 중 시리얼 노이즈로 "READY 4a" 같은 깨진 줄이 올 수 있다.
                        # 예외를 던지지 않고 실패한 핸드셰이크 시도로 취급, 계속 기다린다.
                        print(f"[타일] 경고: 손상된 READY 줄 무시 ({line!r})")
                        continue
                else:
                    servo_count = 0
                self.servo_count = servo_count
                self.simulated = False
                print(f"[타일] 아두이노 연결됨 - 서보 {self.servo_count}개")
                return self.servo_count

        print(f"[타일] 경고: {port} 에서 READY 응답이 오지 않았습니다 - 시뮬레이션 모드.")
        self._close_serial()
        return self._fall_back_to_simulation()

    def _fall_back_to_simulation(self):
        self.simulated = True
        self.servo_count = 0
        return 0

    # --- 명령 ---

    def fire(self, tiles):
        """지정한 타일들을 동시에 작동시킨다. ACK 확인 여부를 반환한다."""
        if not tiles:
            return False
        payload = ",".join(str(t) for t in sorted(tiles))
        return self._command(f"FIRE {payload}", f"OK FIRE {payload}")

    def reset(self):
        """작동 중인 서보를 전부 원위치로 되돌린다."""
        return self._command("RESET", "OK RESET")

    def ping(self):
        return self._command("PING", "OK PING")

    def close(self):
        self._close_serial()

    # --- 내부 ---

    def _command(self, command, expected):
        if self.simulated:
            print(f"[모의] {command}")
            return False

        try:
            self._serial.write((command + "\n").encode("ascii"))
        except Exception as exc:
            print(f"[타일] 경고: '{command}' 전송 실패 ({exc})")
            return False

        deadline = time.monotonic() + RESPONSE_TIMEOUT
        while time.monotonic() < deadline:
            line = self._read_line()
            if line is None:
                time.sleep(POLL_INTERVAL)  # 아직 못 읽었으면 잠깐 쉬었다가 다시 시도
                continue
            if line == expected:
                return True
            print(f"[타일] 경고: 예상과 다른 응답 {line!r} (기대: {expected!r})")
            return False

        print(f"[타일] 경고: '{command}' 응답 시간 초과")
        return False

    def _read_line(self):
        """한 줄을 읽는다. 빈 줄과 '#' 주석은 None 으로 걸러낸다."""
        try:
            raw = self._serial.readline()
        except Exception:
            return None
        if not raw:
            return None
        line = raw.decode("ascii", errors="replace").strip()
        if not line or line.startswith("#"):
            return None
        return line

    def _close_serial(self):
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
