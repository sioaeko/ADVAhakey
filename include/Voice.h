#pragma once
#include <atomic>
extern std::atomic<bool> micRequested, micActive;
extern std::atomic<uint32_t> micHeartbeat;
extern std::atomic<unsigned> micLevel, micError;
void beginVoice();
void pollVoiceHost();

void reportVoice();
