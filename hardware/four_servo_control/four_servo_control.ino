#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

#define NUM_SERVOS 4
const int SERVO_CH[NUM_SERVOS] = {1, 3, 5, 7};  // 모터 1~4가 연결된 채널

// 일반적인 서보 기준값 (필요시 미세조정)
#define SERVO_MIN  102    // 약 0도, 0.5ms 펄스
#define SERVO_MAX  512    // 약 180도, 2.5ms 펄스

#define HOME_ANGLE   0     // 초기/복귀 위치
#define MOVE_ANGLE   60   // 작동 위치

bool moved[NUM_SERVOS] = {false, false, false, false};  // 각 모터가 원위치가 아닌 상태인지

int angleToPulse(int angle) {
  return map(angle, 0, 180, SERVO_MIN, SERVO_MAX);
}

void moveServo(int index, int angle) {
  pwm.setPWM(SERVO_CH[index], 0, angleToPulse(angle));
}

void setup() {
  Serial.begin(9600);
  pwm.begin();
  pwm.setPWMFreq(50);   // 서보는 50Hz
  delay(500);

  for (int i = 0; i < NUM_SERVOS; i++) {
    moveServo(i, HOME_ANGLE);
  }

  Serial.println("초기화 완료. 모터 4개 모두 0도로 고정.");
  Serial.println("1~4 입력: 해당 모터 작동, 0 입력: 작동 중인 모터 전부 원위치");
}

void loop() {
  if (Serial.available() > 0) {
    char c = Serial.read();

    if (c >= '1' && c <= '4') {
      int index = c - '1';
      moveServo(index, MOVE_ANGLE);
      moved[index] = true;
      Serial.print(index + 1);
      Serial.println("번 모터 작동");
    } else if (c == '0') {
      for (int i = 0; i < NUM_SERVOS; i++) {
        if (moved[i]) {
          moveServo(i, HOME_ANGLE);
          moved[i] = false;
          Serial.print(i + 1);
          Serial.println("번 모터 원위치 복귀");
        }
      }
    }
  }
}
