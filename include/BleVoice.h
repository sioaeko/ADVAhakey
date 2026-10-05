#pragma once
#include <stddef.h>
#include <stdint.h>
class BLEServer;
void setupBleVoice(BLEServer* server);
void disconnectBleVoice(uint16_t connection);
bool bleVoiceReady();
bool startBleVoice();
bool sendBleVoice(const uint8_t* data, size_t length);
bool finishBleVoice();
void reportBleVoice();
