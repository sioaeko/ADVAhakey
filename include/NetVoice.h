#pragma once
#include "NetConfig.h"
#include <atomic>
extern std::atomic<unsigned> netState;
void beginNetwork();
NetConfig getNetworkConfig();
bool saveNetworkConfig(const NetConfig& c);
void pollNetwork(bool reconnect=true);
bool networkReady();
bool sendNetwork(const uint8_t* p,size_t n);
bool networkUi(uint64_t raw);
bool networkUiVisible();

extern std::atomic<bool> networkEnabled;
extern std::atomic<unsigned> netPhase,voiceStackFree;
void enableNetwork();

void reportNetwork();
