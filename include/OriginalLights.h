#pragma once
#include <stdint.h>
namespace aha {
struct LightRGB {uint8_t r,g,b;};
void originalLightFrame(uint8_t effect,uint8_t brightness,LightRGB (&out)[8]);
constexpr uint8_t OriginalEffects[9]={11,5,1,1,1,6,6,7,0};
}
