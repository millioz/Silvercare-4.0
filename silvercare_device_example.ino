/*
  SilverCare ESP32 button-to-dashboard starter
  - Update Wi-Fi credentials and SERVER_BASE.
  - Put the patient's device token in DEVICE_TOKEN.
  - This example polls for a pending event and confirms it when the button is pressed.
  - Example pins from the supplied project notes: button GPIO 23, buzzer GPIO 19.
  - Verify your actual board wiring and use a suitable pull-up circuit before powering.
*/
#include <WiFi.h>
#include <HTTPClient.h>

const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* SERVER_BASE = "http://192.168.1.10:5000"; // Flask computer's LAN address
const char* DEVICE_TOKEN = "PASTE_PATIENT_DEVICE_TOKEN_HERE";
const int BUTTON_PIN = 23;
const int BUZZER_PIN = 19;

unsigned long lastPoll = 0;
const unsigned long POLL_INTERVAL_MS = 15000;
int pendingEventId = -1;
bool lastButtonState = HIGH;

void fetchPending() {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(String(SERVER_BASE) + "/api/device/next");
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  int code = http.GET();
  if (code == 200) {
    String body = http.getString();
    int dueKey = body.indexOf("\"due\":[");
    int key = dueKey >= 0 ? body.indexOf("\"id\":", dueKey) : -1;
    if (key >= 0) {
      int start = key + 5;
      while (start < body.length() && (body[start] == ' ' || body[start] == '\t')) start++;
      int end = start;
      while (end < body.length() && isDigit(body[end])) end++;
      pendingEventId = body.substring(start, end).toInt();
    } else {
      pendingEventId = -1; // no reminder is currently due
    }
  }
  http.end();
}

void sendConfirmation(int eventId) {
  if (WiFi.status() != WL_CONNECTED || eventId < 0) return;
  HTTPClient http;
  http.begin(String(SERVER_BASE) + "/api/device/confirm");
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  String payload = String("{\"event_id\":") + eventId + "}";
  int code = http.POST(payload);
  if (code >= 200 && code < 300) {
    Serial.println("SilverCare confirmation sent.");
    pendingEventId = -1;
  } else {
    Serial.printf("Confirmation failed: HTTP %d\n", code);
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  Serial.println("\nSilverCare device connected.");
  fetchPending();
}

void loop() {
  if (millis() - lastPoll >= POLL_INTERVAL_MS) {
    lastPoll = millis();
    fetchPending();
    if (pendingEventId >= 0) {
      digitalWrite(BUZZER_PIN, HIGH); delay(100); digitalWrite(BUZZER_PIN, LOW);
    }
  }
  bool buttonState = digitalRead(BUTTON_PIN);
  if (lastButtonState == HIGH && buttonState == LOW) {
    if (pendingEventId >= 0) sendConfirmation(pendingEventId);
    delay(40); // basic debounce; use a non-blocking debounce in a production build
  }
  lastButtonState = buttonState;
}
