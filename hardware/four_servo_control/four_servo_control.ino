#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
// strtok, strcmp, strncmp / atoi. Arduino 코어가 전이적으로 끌어오는 경우가 많지만
// 보드와 코어 버전에 따라 다르므로 명시한다.
#include <string.h>
#include <stdlib.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

#define NUM_SERVOS 4
const int SERVO_CH[NUM_SERVOS] = {1, 3, 5, 7};  // 타일 0~3 이 연결된 PCA9685 채널

// 일반적인 서보 기준값 (필요시 미세조정)
#define SERVO_MIN  102    // 약 0도, 0.5ms 펄스
#define SERVO_MAX  512    // 약 180도, 2.5ms 펄스

#define HOME_ANGLE   0     // 초기/복귀 위치
#define MOVE_ANGLE  60     // 작동 위치

bool moved[NUM_SERVOS] = {false, false, false, false};

// 줄 단위 프로토콜용 입력 버퍼
#define BUF_SIZE 64
char buf[BUF_SIZE];
int bufLen = 0;

int angleToPulse(int angle) {
  return map(angle, 0, 180, SERVO_MIN, SERVO_MAX);
}

void moveServo(int index, int angle) {
  pwm.setPWM(SERVO_CH[index], 0, angleToPulse(angle));
}

bool isAllDigits(const char *s) {
  if (*s == '\0') return false;
  for (const char *p = s; *p; p++) {
    if (*p < '0' || *p > '9') return false;
  }
  return true;
}

// "0,2,3" 형식의 인자를 받아 해당 타일을 동시에 작동시킨다.
// 하나라도 잘못된 값이 있으면 아무것도 움직이지 않고 ERR 을 반환한다.
void handleFire(char *args) {
  int wanted[NUM_SERVOS];
  int count = 0;

  char *token = strtok(args, ",");
  while (token != NULL) {
    while (*token == ' ') token++;
    if (!isAllDigits(token)) {
      Serial.println("ERR non-numeric tile");
      return;
    }
    int idx = atoi(token);
    if (idx < 0 || idx >= NUM_SERVOS) {
      Serial.println("ERR tile out of range");
      return;
    }
    if (count >= NUM_SERVOS) {
      Serial.println("ERR too many tiles");
      return;
    }
    wanted[count++] = idx;
    token = strtok(NULL, ",");
  }

  if (count == 0) {
    Serial.println("ERR no tiles");
    return;
  }

  for (int i = 0; i < count; i++) {
    moveServo(wanted[i], MOVE_ANGLE);
    moved[wanted[i]] = true;
  }

  // 받은 인자를 그대로 되돌려준다. 파이썬이 "보낸 것"과 아두이노가 "이해한 것"의
  // 일치를 확인할 수 있어야 한다.
  Serial.print("OK FIRE ");
  for (int i = 0; i < count; i++) {
    if (i > 0) Serial.print(",");
    Serial.print(wanted[i]);
  }
  Serial.println();
}

void handleReset() {
  for (int i = 0; i < NUM_SERVOS; i++) {
    if (moved[i]) {
      moveServo(i, HOME_ANGLE);
      moved[i] = false;
    }
  }
  Serial.println("OK RESET");
}

void handleLine(char *line) {
  if (line[0] == '\0') return;

  if (strncmp(line, "FIRE", 4) == 0 && (line[4] == ' ' || line[4] == '\0')) {
    char *args = line + 4;
    while (*args == ' ') args++;
    handleFire(args);
  } else if (strcmp(line, "RESET") == 0) {
    handleReset();
  } else if (strcmp(line, "PING") == 0) {
    Serial.println("OK PING");
  } else {
    Serial.print("ERR unknown command: ");
    Serial.println(line);
  }
}

void setup() {
  Serial.begin(115200);
  pwm.begin();
  pwm.setPWMFreq(50);   // 서보는 50Hz
  delay(500);

  for (int i = 0; i < NUM_SERVOS; i++) {
    moveServo(i, HOME_ANGLE);
  }

  // '#' 로 시작하는 줄은 파이썬 파서가 무시한다. 사람이 읽을 안내문을 남겨도 된다.
  Serial.println("# 초기화 완료. 타일 0~3 모두 HOME_ANGLE 로 고정.");
  Serial.println("# 명령: FIRE 0,2 / RESET / PING");
  Serial.print("READY ");
  Serial.println(NUM_SERVOS);
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      buf[bufLen] = '\0';
      handleLine(buf);
      bufLen = 0;
    } else if (bufLen < BUF_SIZE - 1) {
      buf[bufLen++] = c;
    }
  }
}
