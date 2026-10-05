#pragma once
#include <stdint.h>
namespace aha {
// Only physical button events may arm this gate. Never persist AUTO.
class Gate {
 uint8_t value_=1; uint32_t started_=0; bool held_=false, fired_=false;
 public:
 uint8_t value() const {return value_;}
 void reset(){value_=1;held_=false;fired_=false;}
 void press(uint32_t now){value_=1;started_=now;held_=true;fired_=false;}
 void release(){held_=false;}
 void tick(uint32_t now,bool connected){
  if(!connected){reset();return;}
  if(held_&&!fired_&&uint32_t(now-started_)>=1500){value_=0;fired_=true;}
 }
};
}
