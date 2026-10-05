#pragma once
#include <stdint.h>
#include <stddef.h>
namespace aha {
// Constant ADC samples for >=400ms indicate a stuck converter, not quiet speech.
class VoiceHealth {
 unsigned stuckSamples=0;
 public:
 bool observe(const int16_t* samples,size_t count){
  bool constant=count!=0;for(size_t i=1;i<count;i++)if(samples[i]!=samples[0]){constant=false;break;}
  stuckSamples=constant?stuckSamples+unsigned(count):0;
  return stuckSamples<6400;
 }
};
}
